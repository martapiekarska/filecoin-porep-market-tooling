import base64

import cbor2
import click
import requests

from cli.services.contracts.client_contract import Client, DataCapTypes
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket

EPOCHS_PER_DAY = 2880
TERM_MAX_EPOCHS = 5 * 365 * EPOCHS_PER_DAY  # 5 years hard cap
DATACAP_UNIT = 10 ** 18  # mirrors 1 ether in Solidity


@click.command()
@click.argument('deal_id', type=int)
# @click.option('--private-key', required=True, envvar='PRIVATE_KEY', help='Client wallet private key')
@click.option('--dry-run', is_flag=True, default=False, help='Print transfer params without broadcasting')
def prepare_batches(deal_id: int, dry_run: bool):
    """
    Send DataCap transfers for each piece in a deal, batched in groups of 10.
    """
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
    term_min = deal.terms.duration_days * EPOCHS_PER_DAY
    client = Client()

    for batch_idx, batch in enumerate(batches):
        click.echo(f"\nBatch {batch_idx + 1}/{len(batches)} ({len(batch)} pieces)")
        for piece_str in batch:
            params = build_transfer_params(
                piece_str,
                provider_id=deal.provider_id,
                term_min=term_min,
                term_max=TERM_MAX_EPOCHS,
                expiration=deal.end_epoch,
            )
            if dry_run:
                click.echo(f"to={params.to}  amount={params.amount[0].hex()}  operator_data={params.operator_data.hex()}")
            else:
                click.echo('production alert')
                # tx_hash = client.transfer(params, deal_id, deal_completed, private_key)
                # click.echo(f"  {piece_cid}: tx={tx_hash}  deal_completed={deal_completed}")
        click.echo(f"Batch {batch_idx + 1} done.")


def batch_pieces(pieces: list[dict]) -> list[list[str]]:
    result = [
        [f"{p['pieceCid']}:{p['pieceSize']}:false" for p in pieces[i:i + 10]]
        for i in range(0, len(pieces), 10)
    ]
    result[-1][-1] = result[-1][-1].replace(':false', ':true')
    return result


def decompose_piece_str(piece_str: str) -> tuple[str, int, bool]:
    cid, size, completed = piece_str.rsplit(':', 2)
    return cid, int(size), completed == 'true'


def build_operator_data(provider_id: int, piece_cid: str, size: int, term_min: int, term_max: int, expiration: int) -> bytes:
    return cbor2.dumps([
        [[provider_id, piece_cid, size, term_min, term_max, expiration]],
        [],
    ])


def build_transfer_params(piece_str: str, provider_id: int, term_min: int, term_max: int, expiration: int) -> DataCapTypes.TransferParams:
    piece_cid, piece_size, deal_completed = decompose_piece_str(piece_str)
    return DataCapTypes.TransferParams(
        to=provider_id,
        amount=(_uint_to_bigint_bytes(piece_size * DATACAP_UNIT), False),
        operator_data=build_operator_data(provider_id, piece_cid, piece_size, term_min, term_max, expiration),
    )

def _uint_to_bigint_bytes(value: int) -> bytes:
    if value == 0:
        return b'\x00'
    return value.to_bytes((value.bit_length() + 7) // 8, 'big')
