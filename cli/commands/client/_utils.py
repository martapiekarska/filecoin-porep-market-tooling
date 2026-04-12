import time
import click

from eth_account.datastructures import SignedMessage
from web3.auto import w3
from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market import PoRepMarketDealProposal, PoRepMarketDealState
from cli.services.contracts.usdc_token import USDCToken


def get_client_deals(client_address: str, state: PoRepMarketDealState = None) -> list[PoRepMarketDealProposal]:
    all_deals = commands_utils.get_all_deals(state)
    return [deal for deal in all_deals if deal.client_address == client_address]


# TODO verify this
def calculate_deposit_amount_for_deal(deal: PoRepMarketDealProposal, deposit_for_months: int) -> int:
    deal_size_bytes = deal.terms.deal_size_bytes
    deal_size_sectors = deal_size_bytes / (32 * 1024 ** 2)
    return int(deal_size_sectors * deal.terms.price_per_sector_per_month) * deposit_for_months


def get_permit_deadline() -> int:
    return int(time.time()) + 3600


def sign_filecoinpay_permit(amount: int, permit_deadline: int, from_private_key: str) -> SignedMessage:
    token_name = USDCToken().name()
    from_address = w3.eth.account.from_key(from_private_key).address

    signed_msg = w3.eth.account.sign_typed_data(
        domain_data={
            'name': token_name,
            'version': "1",
            'chainId': commands_utils.get_chain_id(),
            'verifyingContract': utils.get_env('USDC_TOKEN')
        },
        message_types={
            'Permit': [
                {'name': "owner", 'type': "address"},
                {'name': "spender", 'type': "address"},
                {'name': "value", 'type': "uint256"},
                {'name': "nonce", 'type': "uint256"},
                {'name': "deadline", 'type': "uint256"},
            ]
        },
        message_data={
            'owner': from_address,
            'spender': utils.get_env('FILECOIN_PAY'),
            'value': amount,
            'nonce': USDCToken().nonces(from_address),
            'deadline': permit_deadline
        }, private_key=from_private_key)

    if not signed_msg.v or not signed_msg.r or not signed_msg.s or not signed_msg.signature:
        raise Exception(f"Invalid signature generated for permit: {signed_msg}")

    click.echo(f"Message signed for permit: {signed_msg.signature.hex()}")
    return signed_msg
