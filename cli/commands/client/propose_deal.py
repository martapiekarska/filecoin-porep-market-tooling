import sys

import click

from cli.commands import utils as commands_utils
from cli.commands.client import _repair
from cli.commands.client._client import client_signer
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
              help="FCSS repair: also make a one-off payment for the new SP's paid retrieval of the data from a healthy SP.  [default: false]")
@click.option("--repair-of", type=click.IntRange(min=1),
              help="With --repair: deal ID being repaired; MANIFEST_URL must serve the same manifest (see `client repair-manifest`).")
@click.option("--repair-provider-id",
              help="With --repair: optional provider (miner actor) ID of the new SP expected to get the deal; "
                   "the repair retrieval is not paid if the deal is assigned to another SP.")
@click.option("--repair-price-per-gib", type=click.FloatRange(min=0, min_open=True),
              help="With --repair: healthy SP's sp-proxy rate in decimal --payment-token tokens per GiB (e.g., 0.01).")
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
                 repair_provider_id: str | None = None,
                 repair_price_per_gib: float | None = None):
    """
    Interactively propose a deal from MANIFEST_URL with the specified parameters.

    \b
    1. Fetch and validate manifest from a given MANIFEST_URL,
    2. prepare and confirm deal proposal details,
    3. propose deal on-chain via PoRep Market contract,
    4. with --repair: deposit the one-off retrieval cost into the FileCoinPay account of the
       new deal's SP payee (see `client pay-repair-retrieval`).

    MANIFEST_URL - URL of the deal manifest file to use.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    required_repair_options = {"--repair-of": repair_of,
                               "--repair-price-per-gib": repair_price_per_gib}
    repair_options = {**required_repair_options, "--repair-provider-id": repair_provider_id}

    if repair:
        missing = [name for name, value in required_repair_options.items() if value is None]
        if missing:
            raise click.UsageError(f"--repair requires {', '.join(missing)}")

        # check before proposing, so a wrong manifest never creates a deal
        assert repair_of is not None
        _, raw_manifest = commands_utils.fetch_manifest(manifest_url, show_manifest=False, quiet=True)
        if bytes(commands_utils.hash_manifest(raw_manifest)) != bytes(PoRepMarketViewHelper().get_deal_view(repair_of).data.manifest_hash):
            raise click.ClickException(f"Manifest at {manifest_url} does not match deal ID {repair_of} manifest; "
                                       f"use `{sys.argv[0]} client repair-manifest {repair_of}` to prepare it.")

    elif any(value is not None for value in repair_options.values()):
        raise click.UsageError(f"{', '.join(name for name, value in repair_options.items() if value is not None)}: only valid with --repair")

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

    if repair:
        assert repair_price_per_gib
        retry_command = (f"`{sys.argv[0]} client pay-repair-retrieval {deal_id or '<deal-id>'} --price-per-gib {repair_price_per_gib} "
                         f"--repair-of {repair_of}" + (f" --provider-id {repair_provider_id}" if repair_provider_id else "") + "`")

        # e.g. the proposal ran as dry run after declining the final confirmation
        if deal_id is None:
            click.echo(f"\nNo deal created; repair retrieval not paid. Once the deal exists, pay it with {retry_command}")
            return

        click.echo(f"\nFunding repair retrieval for deal ID {deal_id} (if this step fails, retry with {retry_command})")
        _repair.pay_repair_retrieval(deal_id, repair_price_per_gib, repair_of, repair_provider_id, payment_token)


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
