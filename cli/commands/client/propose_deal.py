import sys
from decimal import Decimal

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.client import _repair
from cli.commands.client._client import client_signer
from cli.commands.repair_utils import DecimalAmount, find_healthy_source, get_manifest_repair_source
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.porep_market import PoRepMarketDealType
from cli.services.contracts.porep_market_view_helper import PoRepMarketViewHelper
from cli.services.contracts.usdc_token import USDCToken
from cli.services.self_update import SelfUpdateService
from cli.services.web3_service import EthAddress


@click.command()
@click.argument("manifest_url")
@click.option("--price-per-tib-per-month", type=click.FloatRange(min=0, min_open=True), required=True,
              prompt="Enter maximum monthly price per 1 TiB in decimal format in given --payment-token tokens (e.g., 1.5 for 1.5 USDC)",
              help="Maximum monthly price per 1 TiB in decimal format in given --payment-token tokens. (e.g., 1.5 for 1.5 USDC).")
@click.option("--duration-months", type=click.IntRange(min=6), required=True,
              prompt="Enter deal duration in months (minimum 6 months)",
              help="Deal duration in months. Minimum supported is 6 months.")
@click.option("--payment-token", envvar="USDC_TOKEN", required=True,
              prompt="Enter address of the ERC20 token to pay with",
              help="Address of the ERC20 token to pay with.  [default: USDC_TOKEN env var]")
@click.option("--deal-type", required=True,
              type=click.Choice(PoRepMarketDealType.to_selectable_string_list(), case_sensitive=False),
              prompt="Enter type of the deal to propose",
              help="Type of the deal to propose.")
@click.option("--retrievability-pct", type=click.IntRange(0, 100), required=True,
              prompt="Enter retrievability guarantee in percentage; 0 means \"don't care\"",
              help="Retrievability guarantee in percentage; 0 means \"don't care\".")
@click.option("--bandwidth-mbps", type=click.IntRange(0, 64000), required=True,
              prompt="Enter bandwidth guarantee in Mbps; 0 means \"don't care\"",
              help="Bandwidth guarantee in Mbps; 0 means \"don't care\".")
@click.option("--latency-ms", type=click.IntRange(min=0), required=True,
              prompt="Enter latency guarantee in milliseconds; 0 means \"don't care\"",
              help="Latency guarantee in milliseconds; 0 means \"don't care\".")
@click.option("--indexing-pct", type=click.IntRange(0, 100), required=True,
              prompt="Enter IPNI indexing guarantee in percentage; 0 means \"don't care\"",
              help="IPNI indexing guarantee in percentage; 0 means \"don't care\".")
@click.option("--repair", is_flag=True, default=False,
              help="FCSS repair: also pay the one-off retrieval of the data from a healthy SP for the SP the deal is matched to.  [default: false]")
@click.option("--repair-of", type=click.IntRange(min=1),
              help="With --repair: deal ID being repaired; MANIFEST_URL must serve the same manifest (e.g. that deal's own manifest URL).")
@click.option("--repair-legacy", is_flag=True, default=False,
              help="Legacy (v1) repair: like --repair, but the healthy source is given with --repair-source-url and must match "
                   "the source embedded in MANIFEST_URL (see `client prepare-legacy-repair`); no repaired deal lookup.  [default: false]")
@click.option("--repair-source-url",
              help="With --repair, override: base URL of the healthy SP's piece server / sp-proxy "
                   "[default: auto-detected from other providers' deals for the same dataset]. Required with --repair-legacy.")
@click.option("--repair-price-per-gib", type=DecimalAmount(min_open=True),
              help="With --repair / --repair-legacy, override: retrieval price in decimal --payment-token tokens per GiB.  "
                   "[default: quoted by the healthy SP]")
def propose_deal(manifest_url: str,
                 retrievability_pct: int,
                 bandwidth_mbps: int,
                 price_per_tib_per_month: float,
                 duration_months: int,
                 latency_ms: int,
                 indexing_pct: int,
                 payment_token: str,
                 deal_type: str,
                 repair: bool = False,
                 repair_of: int | None = None,
                 repair_legacy: bool = False,
                 repair_source_url: str | None = None,
                 repair_price_per_gib: Decimal | None = None):
    """
    Interactively propose a deal from MANIFEST_URL with the specified parameters.

    \b
    1. Fetch and validate manifest from a given MANIFEST_URL,
    2. with --repair: find a healthy SP serving the repaired dataset and its retrieval price
       (with --repair-legacy: check the given source and read its price),
    3. prepare and confirm deal proposal details,
    4. propose deal on-chain via PoRep Market contract (the SP is matched as for any other deal),
    5. with --repair / --repair-legacy: deposit the one-off retrieval cost into the FileCoinPay account of the
       matched SP's payee (see `client pay-repair-retrieval`).

    MANIFEST_URL - URL of the deal manifest file to use.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    repair_options = {"--repair-of": repair_of,
                      "--repair-source-url": repair_source_url,
                      "--repair-price-per-gib": repair_price_per_gib}
    source = None

    if repair and repair_legacy:
        raise click.UsageError("Use either --repair or --repair-legacy, not both")

    if repair_legacy:
        if repair_source_url is None:
            raise click.UsageError("--repair-legacy requires --repair-source-url")

        if repair_of is not None:
            raise click.UsageError("--repair-of is not used with --repair-legacy")

        manifest, _ = commands_utils.fetch_manifest(manifest_url, show_manifest=False, quiet=True)

        # the new SP fetches from the source embedded in the deal manifest, so it must be the one the client checks and pays for
        if get_manifest_repair_source(manifest) != repair_source_url.rstrip("/"):
            raise click.ClickException(f"Manifest at {manifest_url} has repair source {get_manifest_repair_source(manifest)!r}, "
                                       f"not {repair_source_url!r}; prepare it with `{sys.argv[0]} client prepare-legacy-repair`.")

        if repair_price_per_gib is None:
            source = find_healthy_source(b"", manifest[0]["pieces"], set(), repair_source_url)

        _echo_repair_cost(manifest[0]["pieces"], repair_price_per_gib if repair_price_per_gib is not None else source.price_per_gib, payment_token)

    elif repair:
        if repair_of is None:
            raise click.UsageError("--repair requires --repair-of")

        repaired_deal = PoRepMarketViewHelper().get_deal_view(repair_of)
        _repair.ensure_repairable(repaired_deal)

        # check before proposing, so a wrong manifest never creates a deal
        manifest, raw_manifest = commands_utils.fetch_manifest(manifest_url, show_manifest=False, quiet=True)
        if bytes(commands_utils.hash_manifest(raw_manifest)) != bytes(repaired_deal.data.manifest_hash):
            raise click.ClickException(f"Manifest at {manifest_url} does not match deal ID {repair_of} manifest "
                                       f"{repaired_deal.data.manifest_location}")

        # show the repair cost before the proposal is confirmed
        if repair_price_per_gib is None:
            source = find_healthy_source(repaired_deal.data.manifest_hash, manifest[0]["pieces"],
                                         {repaired_deal.deal.provider_id}, repair_source_url)

        _echo_repair_cost(manifest[0]["pieces"], repair_price_per_gib if repair_price_per_gib is not None else source.price_per_gib, payment_token)

    elif any(value is not None for value in repair_options.values()):
        raise click.UsageError(f"{', '.join(name for name, value in repair_options.items() if value is not None)}: only valid with --repair / --repair-legacy")

    deal_id = commands_utils.propose_deal(client_signer(),
                                          manifest_url,
                                          retrievability_pct,
                                          bandwidth_mbps,
                                          price_per_tib_per_month,
                                          duration_months,
                                          latency_ms,
                                          indexing_pct,
                                          EthAddress.from_any(payment_token),
                                          PoRepMarketDealType.from_web3(deal_type))

    if repair or repair_legacy:
        overrides = (f" --repair-of {repair_of}" if repair_of is not None else "") + \
                    (f" --source-url {repair_source_url}" if repair_source_url else "") + \
                    (f" --price-per-gib {repair_price_per_gib}" if repair_price_per_gib is not None else "")
        retry_command = f"`{sys.argv[0]} client pay-repair-retrieval {deal_id or '<deal-id>'}{overrides}`"

        # e.g. the proposal ran as dry run after declining the final confirmation
        if deal_id is None:
            click.echo(f"\nNo deal created; repair retrieval not paid. Once the deal exists, pay it with {retry_command}")
            return

        click.echo(f"\nFunding repair retrieval for deal ID {deal_id} (if this step fails, retry with {retry_command})")
        _repair.pay_repair_retrieval(deal_id, repair_of, repair_source_url, repair_price_per_gib, payment_token, source)


def _echo_repair_cost(pieces: list[dict], price_per_gib, payment_token: str):
    token = ERC20Contract(EthAddress.from_any(payment_token))
    cost = _repair.estimate_retrieval_cost(pieces, _repair.price_to_wei(price_per_gib, token.decimals()))
    click.echo(f"\nEstimated one-off repair retrieval cost, paid after the deal is matched: "
               f"{utils.str_from_wei(cost, token.decimals())} {token.symbol()}\n")


@click.command(hidden=True)
@click.argument("manifest_url")
def propose_deal_mocked(manifest_url: str):
    retrievability_pct = 1
    bandwidth_mbps = 1
    price_per_tib_per_month = 1  # 1 USDC per TiB per month
    duration_months = 6
    latency_ms = 999
    indexing_pct = 1

    commands_utils.propose_deal(client_signer(),
                                manifest_url,
                                retrievability_pct,
                                bandwidth_mbps,
                                price_per_tib_per_month,
                                duration_months,
                                latency_ms,
                                indexing_pct,
                                USDCToken().address(),
                                PoRepMarketDealType.PUBLIC)
