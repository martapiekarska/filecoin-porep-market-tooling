import click
import humanfriendly
import requests
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.client import _utils as client_utils
from cli.commands.client._client import client_private_key
from cli.services.contracts.contract_service import ContractService
from cli.services.contracts.porep_market import PoRepMarketDealRequest, PoRepMarketDealTerms, PoRepMarket, PoRepMarketDealState
from cli.services.contracts.sp_registry import SPRegistrySLIThresholds
from cli.services.contracts.usdc_token import USDCToken


def _fetch_manifest(manifest_url: str) -> list[dict]:
    try:
        # download manifest
        manifest = requests.get(manifest_url, timeout=30).json()
        click.echo(f"Manifest downloaded from {manifest_url}")

        # show manifest
        if utils.ask_user_confirm("Show manifest?", default_answer=False):
            _manifest = utils.json_pretty(manifest)
            click.echo_via_pager("\n".join([f"{i + 1}. {line}" for i, line in enumerate(_manifest.splitlines())]))

        click.echo()

        # validate manifest format
        if not (
                manifest and
                isinstance(manifest, list) and
                len(manifest) == 1 and

                manifest[0] and
                isinstance(manifest[0], dict) and
                "pieces" in manifest[0] and

                manifest[0]["pieces"] and
                isinstance(manifest[0]["pieces"], list) and

                all(isinstance(piece, dict) and
                    "pieceType" in piece and
                    "pieceSize" in piece and
                    "preparationId" in piece for piece in
                    manifest[0]["pieces"])
        ):
            raise Exception("Invalid manifest format")

        return manifest
    except Exception as e:
        raise Exception(f"Error fetching manifest: {e}") from e


def _validate_manifest_pieces(manifest: list[dict]) -> list[dict]:
    pieces = manifest[0]["pieces"]

    if not (pieces and isinstance(pieces, list) and len(pieces) > 1):
        raise Exception("No pieces found in manifest")

    data_pieces = [piece for piece in pieces if piece["pieceType"] == "data"]
    dag_pieces = [piece for piece in pieces if piece["pieceType"] == "dag"]

    if len(data_pieces) != len(pieces) - 1 or len(dag_pieces) != 1:
        raise Exception("Invalid manifest pieces: must contain exactly one dag piece and at least one data piece")

    if not all(piece["preparationId"] == pieces[0]["preparationId"] for piece in pieces):
        raise Exception("Invalid preparationId in manifest pieces")

    return manifest


# TODO LATER propose for multiple manifests + state, retry
# TODO LATER validate params here?
# TODO LATER print proposed deal at the end? where do we get deal id from? events only?
def _propose_deal_from_manifest(manifest_url: str,
                                retrievability_bps: int,
                                bandwidth_mbps: int,
                                price_per_sector_per_month: int,
                                duration_months: int,
                                latency_ms: int,
                                indexing_pct: int,
                                from_private_key: str):
    #
    manifest = _validate_manifest_pieces(_fetch_manifest(manifest_url))
    pieces = manifest[0]["pieces"]
    pieces_size_bytes = sum(piece["pieceSize"] for piece in pieces)

    if pieces_size_bytes <= 0:
        raise Exception("Invalid deal size")

    click.echo(f"Found {len(pieces)} pieces with size {pieces_size_bytes} bytes "
               f"({humanfriendly.format_size(pieces_size_bytes)} = {humanfriendly.format_size(pieces_size_bytes, binary=True)} = "
               f"{commands_utils.bytes_to_sectors(pieces_size_bytes)} sectors) "
               f"(including dag piece)")

    # noinspection PyArgumentList
    deal = PoRepMarketDealRequest(
        requirements=SPRegistrySLIThresholds(
            retrievability_bps=retrievability_bps,
            bandwidth_mbps=bandwidth_mbps,
            latency_ms=latency_ms,
            indexing_pct=indexing_pct,
        ),
        terms=PoRepMarketDealTerms(
            deal_size_bytes=pieces_size_bytes,
            price_per_sector_per_month=price_per_sector_per_month,
            duration_days=duration_months * 30,  # PoRep Market smart contracts assumes month == 30 days
        ),
        manifest_location=manifest_url)

    # wait for pending transactions
    from_address = w3.eth.account.from_key(from_private_key).address
    _ = ContractService.get_address_nonce(from_address)

    existing_deals = client_utils.get_client_deals(from_address)

    # warn if any of existing client deals looks similar to the new deal proposal
    for existing_deal in existing_deals:
        is_active = existing_deal.state in [PoRepMarketDealState.PROPOSED, PoRepMarketDealState.ACCEPTED]

        if deal.terms.deal_size_bytes == existing_deal.terms.deal_size_bytes:
            if not utils.ask_user_confirm(f"\nWarning: Client deal with the same deal size "
                                          f"already exists in PoRep Market: {utils.json_pretty(existing_deal)} "
                                          "Continue?", default_answer=not is_active):
                #
                click.echo("Canceled!\n")
                return

        if deal.manifest_location == existing_deal.manifest_location:
            if not utils.ask_user_confirm(
                    f"\nWarning: Client deal with the same manifest location "
                    f"already exists in PoRep Market: {utils.json_pretty(existing_deal)} "
                    "Continue?", default_answer=not is_active):
                #
                click.echo("Canceled!\n")
                return

    token_name = USDCToken().name()
    deal_duration_months = deal.terms.duration_days // 30  # PoRep Market smart contracts assumes month == 30 days

    max_cost_per_month = client_utils.calculate_deposit_amount_for_deal(deal, deposit_for_months=1)
    max_cost_per_month_str = utils.str_from_wei(max_cost_per_month, USDCToken().decimals())

    total_max_cost = max_cost_per_month * deal_duration_months
    total_max_cost_str = utils.str_from_wei(total_max_cost, USDCToken().decimals())

    # TODO LATER print account info (you now have ... at address ...)
    if not utils.ask_user_confirm(f"\nProposing deal: {utils.json_pretty(deal)}"
                                  f" This will cost you maximum of {max_cost_per_month_str} {token_name} per month. "
                                  f"This is a total of {total_max_cost_str} {token_name} for {duration_months} months. "
                                  f"Continue?"):
        click.echo("Canceled!\n")
        return

    tx_hash = PoRepMarket().propose_deal(deal, from_private_key)
    click.echo(f"Created deal proposal from manifest {manifest_url}: {tx_hash}")


@click.command()
@click.argument("manifest-url")
@click.option("--retrievability-bps", type=click.IntRange(0, 10000), required=True,
              help="Retrievability guarantee in bps (basis points, e.g. 7550 = 75.50%); 0 means \"don't care\".")
@click.option("--bandwidth-mbps", type=click.IntRange(0, 64000), required=True,
              help="Bandwidth guarantee in Mbps. Capped at ~64 Gbps.")
# TODO LATER make this price-per-tib-per-month?
@click.option("--price-per-sector-per-month", help="Monthly price per 32 GiB sector in USDC smallest units (wei-equivalent).",
              type=click.IntRange(min=0), required=True)
@click.option("--duration-months", type=click.IntRange(min=6), required=True,
              help="Deal duration in months. Minimum supported is 6 months.")
@click.option("--latency-ms", type=click.IntRange(min=0), required=True,
              help="Latency guarantee in milliseconds.")
@click.option("--indexing-pct", type=click.IntRange(0, 100), default=0, show_default=True,
              help="IPNI indexing guarantee in percentage; 0 means \"don't care\".")
def propose_deal_from_manifest(manifest_url: str,
                               retrievability_bps: int,
                               bandwidth_mbps: int,
                               price_per_sector_per_month: int,
                               duration_months: int,
                               latency_ms: int,
                               indexing_pct: int):
    """
    Interactively propose a deal from MANIFEST_URL with the specified parameters.

    \b
    1. Fetch and validate manifest from a given MANIFEST_URL,
    2. prepare and confirm deal proposal details,
    3. propose deal on-chain via PoRep Market contract.

    MANIFEST_URL - URL of the deal manifest file to download.
    """

    _propose_deal_from_manifest(manifest_url,
                                retrievability_bps,
                                bandwidth_mbps,
                                price_per_sector_per_month,
                                duration_months,
                                latency_ms,
                                indexing_pct,
                                client_private_key())


# TODO LATER remove me
@click.command()
@click.argument("manifest-url", default="http://117.55.199.67:9090/api/preparation/fsboard/piece")
def propose_deal_from_manifest_mocked(manifest_url: str):
    """
    Testing and development purposes.
    """

    retrievability_bps = 10
    bandwidth_mbps = 1
    price_per_sector_per_month = utils.to_wei(2, USDCToken().decimals())  # 2 USDC per sector per month
    duration_months = 3
    latency_ms = 999
    indexing_pct = 1

    _propose_deal_from_manifest(manifest_url,
                                retrievability_bps,
                                bandwidth_mbps,
                                price_per_sector_per_month,
                                duration_months,
                                latency_ms,
                                indexing_pct,
                                client_private_key())
