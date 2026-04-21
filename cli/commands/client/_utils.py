import time
from math import ceil

import click
import requests
from eth_account.datastructures import SignedMessage
from eth_account.types import PrivateKeyType
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import ContractService, Address
from cli.services.contracts.porep_market import PoRepMarketDealProposal, PoRepMarketDealState, PoRepMarketDealRequest
from cli.services.contracts.usdc_token import USDCToken


def get_client_deals(client_address: Address, state: PoRepMarketDealState | None = None) -> list[PoRepMarketDealProposal]:
    all_deals = commands_utils.get_all_deals(state=state)
    return [deal for deal in all_deals if deal.client_address == client_address]


def calculate_deposit_amount_for_deal(deal: PoRepMarketDealRequest, deposit_for_months: int = 1) -> int:
    if deposit_for_months < 0:
        raise Exception("deposit_for_months must be >= 0")

    deal_size_sectors = commands_utils.bytes_to_sectors(deal.terms.deal_size_bytes)
    result = deal_size_sectors * deal.terms.price_per_sector_per_month * deposit_for_months

    if result != ceil(result):
        utils.ask_user_confirm_or_fail(
            f"Calculated deposit amount {result} != {ceil(result)}. Continue?", default_answer=True)

    return ceil(result)


def get_permit_deadline() -> int:
    return int(time.time()) + 3600  # 1 hour


# EIP-712 signing for FileCoinPay permit msg
def sign_filecoinpay_permit(amount: int, permit_deadline: int, from_private_key: PrivateKeyType) -> SignedMessage:
    token_name = USDCToken().name()
    from_address = Address.from_private_key(from_private_key)

    # signed_msg.signature is sensitive info, should never be logged
    signed_msg = w3.eth.account.sign_typed_data(
        domain_data={
            "name": token_name,
            "version": "1",
            "chainId": ContractService.get_chain_id(),
            "verifyingContract": utils.get_env_required("USDC_TOKEN", required_type=Address)
        },
        message_types={
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ]
        },
        message_data={
            "owner": from_address,
            "spender": utils.get_env_required("FILECOIN_PAY", required_type=Address),
            "value": amount,
            "nonce": USDCToken().nonces(from_address),
            "deadline": permit_deadline
        }, private_key=from_private_key)

    if not signed_msg.v or not signed_msg.r or not signed_msg.s or not signed_msg.signature:
        raise Exception("Invalid EIP-712 signature generated for FileCoinPay permit")

    click.echo(f"EIP-712 message signed for FileCoinPay permit: {utils.private_str_to_log_str(signed_msg.signature.hex())}")
    return signed_msg


def fetch_manifest(manifest_url: str, show_manifest: bool | None = None) -> list[dict]:
    click.echo(f"Fetching manifest from {manifest_url}")

    while True:
        try:
            return _fetch_manifest(manifest_url, show_manifest)
        except requests.exceptions.RequestException as e:
            if not utils.ask_user_confirm(f"\nFailed to fetch manifest:\n{e}.\nRetry?", default_answer=True):
                raise Exception(f"Network error while fetching manifest: {e}") from e


def _fetch_manifest(manifest_url: str, show_manifest: bool | None = None) -> list[dict]:
    MINIMUM_DAG_PIECE_SIZE_BYTES = 1024 * 1024  # 1 MiB

    # download manifest
    resp = requests.get(manifest_url, timeout=30)
    resp.raise_for_status()

    try:
        manifest = resp.json()
    except ValueError as e:
        raise ValueError(f"Manifest is not a valid JSON: {e}") from e

    click.echo("Manifest downloaded")

    # show manifest
    if show_manifest or (show_manifest is None and utils.ask_user_confirm("Show manifest?", default_answer=False)):
        _manifest = utils.json_pretty(manifest)
        click.echo_via_pager("\n".join([f"{i + 1}. {line}" for i, line in enumerate(_manifest.splitlines())]))
        click.echo()

    try:
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
                    "pieceCid" in piece and
                    "pieceType" in piece and
                    "pieceSize" in piece and
                    "preparationId" in piece and
                    "attachmentId" in piece
                    for piece in manifest[0]["pieces"])
        ):
            raise ValueError("Invalid manifest format")

        # validate manifest pieces
        pieces = manifest[0]["pieces"]
        data_pieces = [piece for piece in pieces if piece["pieceType"] == "data"]
        dag_pieces = [piece for piece in pieces if piece["pieceType"] == "dag"]

        if len(pieces) <= 1 or len(data_pieces) != len(pieces) - 1 or len(dag_pieces) != 1:
            raise ValueError("Invalid manifest pieces: must contain exactly one dag piece and at least one data piece")

        if not all(piece["preparationId"] == pieces[0]["preparationId"] for piece in pieces):
            raise ValueError("Invalid preparationId in manifest pieces: must be the same for all pieces")

        if not all(piece["attachmentId"] == pieces[0]["attachmentId"] for piece in pieces):
            raise ValueError("Invalid attachmentId in manifest pieces: must be the same for all pieces")

        if dag_pieces[0]["pieceSize"] < MINIMUM_DAG_PIECE_SIZE_BYTES:
            raise ValueError(f"Invalid dag piece size in manifest: must be at least 1 MiB "
                             f"({dag_pieces[0]['pieceSize']} < {MINIMUM_DAG_PIECE_SIZE_BYTES} bytes)")
        #
    except KeyError as e:
        raise ValueError(f"Invalid manifest format: missing key {e}") from e

    return manifest
