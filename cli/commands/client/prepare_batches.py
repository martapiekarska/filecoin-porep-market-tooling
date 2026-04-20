import cbor2
import click
import multibase
from eth_account.types import PrivateKeyType

from cli import utils
from cli.commands.client import _utils as client_utils
from cli.commands.client._client import client_private_key, client_address
from cli.services.contracts.client_contract import ClientContract
from cli.services.contracts.contract_service import ContractService
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket

EPOCHS_PER_DAY = 60 * 24 * 2
EPOCHS_PER_MONTH = EPOCHS_PER_DAY * 30
BATCH_SIZE = 10


def _prepare_batches(deal_id: int, start_batch: int, dry_run: bool | None, from_private_key: PrivateKeyType):
    deal = PoRepMarket().get_deal_proposal(deal_id)

    if deal.state != PoRepMarketDealState.ACCEPTED:
        raise Exception(f"Deal id {deal_id} is not in ACCEPTED state")

    manifest = client_utils.fetch_manifest(deal.manifest_location, show_manifest=False)
    pieces = [piece for attachment in manifest for piece in attachment["pieces"]]
    batches = _batch_pieces(pieces)
    deal_duration = deal.terms.duration_days * EPOCHS_PER_DAY
    client_contract = ClientContract()

    for batch_idx, batch in enumerate(batches):
        current_batch_number = batch_idx + 1

        if current_batch_number < start_batch:
            click.echo(f"Skipping Batch {current_batch_number}/{len(batches)}...")
            continue

        click.echo(f"\nBatch {current_batch_number}/{len(batches)} ({len(batch)} pieces)")

        operator_data = _build_operator_data_batch(
            provider_id=deal.provider_id,
            batch=batch,
            term_min=deal_duration,
            term_max=deal_duration,
            expiration=ContractService.get_block_number() + EPOCHS_PER_MONTH
        )

        total_size = sum(size for _, size in batch)

        params = ClientContract.TransferParams(
            to=(b"\x00\x06",),
            amount=(utils.uint_to_bytes(total_size, size=None), False),
            operator_data=operator_data,
        )

        is_completed = current_batch_number == len(batches)

        if dry_run:
            click.echo(f"to={params.to[0].hex()}  amount={params.amount[0].hex()}  operator_data={params.operator_data.hex()}   is_completed={is_completed}")
        else:
            tx_hash = client_contract.transfer(params, deal_id, is_completed, from_private_key)
            click.echo(f"params: {params}, tx={tx_hash}, deal_completed={is_completed}")

        click.echo(f"Batch {current_batch_number} done.")


@click.command()
@click.argument("deal_id", type=click.IntRange(min=0))
@click.option("--dry-run", is_flag=True, default=False, show_default=True, help="Print transfer params without broadcasting.")
@click.option("--start-batch", type=click.IntRange(min=1), default=1, show_default=True, help="Batch number to start from (1-based index).")
def prepare_batches(deal_id: int, start_batch: int, dry_run: bool | None = None):
    """
    Prepares and optionally sends DDO allocation transactions for a given DEAL_ID in batches.

    DEAL_ID: ID of the deal to prepare batches for.
    """

    ContractService.wait_for_pending_transactions(client_address())

    _prepare_batches(deal_id, start_batch, dry_run, client_private_key())


def _build_operator_data_batch(provider_id: int, batch: list[tuple[str, int]], term_min: int, term_max: int, expiration: int) -> bytes:
    def format_cid_to_cbor_universal(cid_str: str) -> cbor2.CBORTag:
        cid_bytes = multibase.decode(cid_str)
        cid_with_prefix = b"\x00" + cid_bytes
        return cbor2.CBORTag(42, cid_with_prefix)

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


def _batch_pieces(pieces: list[dict]) -> list[list[tuple[str, int]]]:
    result = [
        [(p["pieceCid"], int(p["pieceSize"])) for p in pieces[i:i + BATCH_SIZE]]
        for i in range(0, len(pieces), BATCH_SIZE)
    ]

    return result
