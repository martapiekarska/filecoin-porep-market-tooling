import json

import requests
import click

from urllib.error import URLError, HTTPError
from web3.auto import w3
from cli.commands.client._client import client_private_key
from cli.services.contracts.porep_market import PoRepMarketDealRequest, PoRepMarketDealTerms, PoRepMarket, PoRepMarketDealState
from cli.services.contracts.sp_registry import SPRegistrySLIThresholds
from cli import utils
from cli.commands.client import _utils as client_utils

def _fetch_manifest(manifest_url: str) -> dict:
    try:
        manifest = requests.get(manifest_url).json()
        click.echo(f'Manifest downloaded from {manifest_url}')
        return manifest
    except HTTPError as e:
        raise Exception(f"HTTP error fetching manifest URL: {e.code} {e.reason}")
    except URLError as e:
        raise Exception(f"Network error fetching manifest URL: {e.reason}")
    except json.JSONDecodeError as e:
        raise Exception(f"Response was not valid JSON: {e}")
    except Exception as e:
        raise Exception(f"Error fetching manifest: {e}")

# TODO retry, state, check if already proposed
def _propose_deal_from_manifest(manifest_url: str,
                                retrievability_bps: int,
                                bandwidth_mbps: int,
                                price_per_sector_per_month: int,
                                duration_days: int,
                                latency_ms: int,
                                indexing_pct: int,
                                from_private_key: str):
    manifest = _fetch_manifest(manifest_url)

    if len(manifest) != 1:
        raise Exception(f'Invalid manifest')

    if 'pieces' not in manifest[0] or not len(manifest[0]['pieces']):
        raise Exception(f'Invalid manifest pieces')

    # TODO verify this
    data_pieces = [piece for piece in manifest[0]['pieces'] if piece['pieceType'] == 'data']
    data_pieces_size = sum(piece['pieceSize'] for piece in data_pieces)

    if not all(piece['preparationId'] == data_pieces[0]['preparationId'] for piece in data_pieces):
        raise Exception(f'Invalid preparationId in manifest pieces')

    if not data_pieces_size:
        raise Exception(f'Invalid deal size: {data_pieces_size}')

    click.echo(f"Found {len(data_pieces)} data pieces with size {data_pieces_size} bytes and {len(manifest[0]['pieces']) - len(data_pieces)} other pieces")

    if utils.ask_user_confirm(f"Print manifest?", default_answer=False):
        _manifest = utils.json_pretty(manifest)
        click.echo_via_pager('\n'.join([f"{i+1}. {line}" for i, line in enumerate(_manifest.splitlines())]))

    deal = PoRepMarketDealRequest(
        requirements=SPRegistrySLIThresholds(
            retrievability_bps=retrievability_bps,
            bandwidth_mbps=bandwidth_mbps,
            latency_ms=latency_ms,
            indexing_pct=indexing_pct,
        ),
        terms=PoRepMarketDealTerms(
            deal_size_bytes=data_pieces_size,
            price_per_sector_per_month=price_per_sector_per_month,
            duration_days=duration_days,
        ),
        manifest_location=manifest_url)

    all_deals = client_utils.get_client_deals(w3.eth.account.from_key(from_private_key).address)

    for existing_deal in [deal for deal in all_deals if deal.state in [PoRepMarketDealState.Proposed, PoRepMarketDealState.Accepted]]:
        if deal.terms.deal_size_bytes == existing_deal.terms.deal_size_bytes:
            if not utils.ask_user_confirm(f"\nWarning: Client deal with the same deal size already exists in PoRep Market: {utils.json_pretty(existing_deal)} "
                                          "Continue?", default_answer=False): return

        if deal.manifest_location == existing_deal.manifest_location:
            if not utils.ask_user_confirm(f"\nWarning: Client deal with the same manifest location already exists in PoRep Market: {utils.json_pretty(existing_deal)} "
                                          "Continue?", default_answer=False): return

    if not utils.ask_user_confirm(f"\nProposing deal: {utils.json_pretty(deal)}"): return

    tx_hash = PoRepMarket().propose_deal(deal, from_private_key)
    click.echo(f"Created deal proposal from manifest {manifest_url}: {tx_hash}")


@click.command()
@click.argument('manifest-url')
@click.option('--retrievability-bps', required=True, help='Retrievability guarantee in bps (basis points, e.g. 7550 = 75.50%); 0 means "don\'t care".', type=click.IntRange(0, 10000))
@click.option('--bandwidth-mbps', required=True, help='Bandwidth guarantee in Mbps.', type=click.IntRange(0, 64000))
@click.option('--price-per-sector-per-month', required=True, help='Price per sector per month in tokens.', type=click.IntRange(0, None))
@click.option('--duration-days', required=True, help='Deal duration in days.', type=click.IntRange(1, 1278))
@click.option('--latency-ms', required=True, help='Latency guarantee in milliseconds.', type=click.IntRange(0, None))
@click.option('--indexing-pct', required=True, help='Indexing guarantee in percentage; 0 means "don\'t care".', type=click.IntRange(0, 100))
def propose_deal_from_manifest(manifest_url: str,
                               retrievability_bps: int,
                               bandwidth_mbps: int,
                               price_per_sector_per_month: int,
                               duration_days: int,
                               latency_ms: int,
                               indexing_pct: int):
    """
    Propose a deal from MANIFEST_URL with the specified parameters.

    MANIFEST_URL - URL of the deal manifest file to download.
    """
    _propose_deal_from_manifest(manifest_url,
                                retrievability_bps,
                                bandwidth_mbps,
                                price_per_sector_per_month,
                                duration_days,
                                latency_ms,
                                indexing_pct,
                                client_private_key())


# TODO
@click.command()
@click.argument('manifest-url', default='http://117.55.199.67:9090/api/preparation/1/piece')
def propose_deal_from_manifest_mocked(manifest_url: str):
    """
    Testing and development purposes.
    """
    retrievability_bps = 10
    bandwidth_mbps = 1
    price_per_sector_per_month = 1000
    duration_days = 180
    latency_ms = 999
    indexing_pct = 1

    _propose_deal_from_manifest(manifest_url,
                                retrievability_bps,
                                bandwidth_mbps,
                                price_per_sector_per_month,
                                duration_days,
                                latency_ms,
                                indexing_pct,
                                client_private_key())
