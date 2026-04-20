import cbor2
import click
import requests
import multibase

from cli.services.contracts.client_contract import Client, DataCapTypes
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket
from cli.commands import utils as commands_utils
from cli.commands.client._client import client_private_key

EPOCHS_PER_DAY = 60 * 24 * 2
EPOCHS_PER_MONTH = EPOCHS_PER_DAY * 30
TERM_MAX_EPOCHS = 5 * 365 * EPOCHS_PER_DAY
BATCH_SIZE = 10


@click.command()
@click.argument('deal_id', type=int)
# @click.option('--private-key', required=True, envvar='PRIVATE_KEY', help='Client wallet private key')
@click.option('--dry-run', is_flag=True, default=False, help='Print transfer params without broadcasting')
@click.option('--start-batch', type=int, default=1, help='Batch number to start from (1-based index)')
def prepare_batches(deal_id: int, dry_run: bool, start_batch: int):
    deal = PoRepMarket().get_deal_proposal(deal_id)
    if not deal:
        raise Exception(f"Deal id {deal_id} not found")
    if deal.state != PoRepMarketDealState.ACCEPTED:
        raise Exception(f"Deal id {deal_id} is not in accepted state")

    manifest = requests.get(deal.manifest_location).json()
    
    if not manifest:
        raise Exception(f"Manifest not found for deal id {deal_id}")

    pieces = [piece for attachment in manifest for piece in attachment['pieces']]
    if not pieces:
        raise Exception(f"No pieces found for deal id {deal_id}")

    batches = batch_pieces(pieces)
    deal_duration = deal.terms.duration_days * EPOCHS_PER_DAY
    client = Client()

    for batch_idx, batch in enumerate(batches):
        current_batch_number = batch_idx + 1
        
        if current_batch_number < start_batch:
            click.echo(f"Skipping Batch {current_batch_number}/{len(batches)}...")
            continue

        click.echo(f"\nBatch {current_batch_number}/{len(batches)} ({len(batch)} pieces)")

        operator_data = build_operator_data_batch(
            provider_id=deal.provider_id,
            batch=batch,
            term_min=deal_duration,
            term_max=deal_duration,
            expiration=commands_utils.get_block_number() + EPOCHS_PER_MONTH
        )

        total_size = sum(size for _, size in batch)

        params = DataCapTypes.TransferParams(
            to=(b"\x00\x06",),
            amount=(_uint_to_bigint_bytes(total_size), False),
            operator_data=operator_data,
        )

        isCompleted = current_batch_number == len(batches)

        if dry_run:
            click.echo(f"to={params.to[0].hex()}  amount={params.amount[0].hex()}  operator_data={params.operator_data.hex()}   isCompleted={isCompleted}")
        else:
            click.echo('production alert')
            tx_hash = client.transfer(params, deal_id, isCompleted, client_private_key())
            click.echo(f"params: {params}, tx={tx_hash}, deal_completed={isCompleted}")
        
        click.echo(f"Batch {current_batch_number} done.")


def build_operator_data_batch(provider_id: int, batch: list[tuple[str, int]], term_min: int, term_max: int, expiration: int) -> bytes:
    entries = []

    for piece_cid, size in batch:
        entries.append([
            provider_id,
            format_cid_to_cbor_universal(piece_cid),
            size,
            term_min,
            term_max,
            expiration
        ])

    return cbor2.dumps([
        entries,
        [],
    ])


def batch_pieces(pieces: list[dict]) -> list[list[tuple[str, int]]]:
    result = [
        [(p['pieceCid'], int(p['pieceSize'])) for p in pieces[i:i + BATCH_SIZE]]
        for i in range(0, len(pieces), BATCH_SIZE)
    ]
    return result


def _uint_to_bigint_bytes(value: int) -> bytes:
    if value == 0:
        return b'\x00'
    return value.to_bytes((value.bit_length() + 7) // 8, 'big')


def format_cid_to_cbor_universal(cid_str: str):
    cid_bytes = multibase.decode(cid_str)
    cid_with_prefix = b'\x00' + cid_bytes
    return cbor2.CBORTag(42, cid_with_prefix)