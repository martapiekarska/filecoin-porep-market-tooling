import sys

import click

from web3.auto import w3
from cli.commands.client._client import client_private_key
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.filecoinpay_validator import FileCoinPayValidator
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal
from cli.services.contracts.usdc_token import USDCToken
from cli.services.contracts.validator_factory import ValidatorFactory
from cli import utils
from cli.commands.client import _utils as client_utils


@click.command()
def init_accepted_deals():
    """
    Interactively handle accepted deals.

    \b
    1. deploy and setting validator,
    2. deposit FileCoin pay funds and approving operator,
    3. initialize FileCoinPay rail.
    """
    _init_accepted_deals(client_private_key())


def _init_accepted_deals(from_private_key: str):
    from_address = w3.eth.account.from_key(from_private_key).address
    accepted_deals = client_utils.get_client_deals(from_address, PoRepMarketDealState.Accepted)
    click.echo(f"Found {len(accepted_deals)} accepted deals for client_address {from_address}\n")

    for deal in accepted_deals:
        click.echo(f"\nDeal id {deal.deal_id}: {utils.json_pretty(deal)}\n")

        _deploy_and_set_validator(deal, from_private_key)
        _deposit_and_approve_operator(deal, from_private_key)
        _initialize_rail(deal, from_private_key)

    click.echo(f"Run {sys.argv[0]} client deposit-for-all-deals to make sure you have enough FileCoin pay funds deposited for all your accepted deals")


def __get_validator_address_for_deal(deal: PoRepMarketDealProposal) -> str:
    result = ValidatorFactory().get_instance(deal.deal_id)

    if result != deal.validator_address:
        raise Exception(f"Validator address {result} does not match expected {deal.validator_address} for deal id {deal.deal_id}")

    return result


def _deploy_and_set_validator(deal: PoRepMarketDealProposal, from_private_key: str) -> str | None:
    if deal.validator_address:
        click.echo(f"Validator already set for deal id {deal.deal_id}: {deal.validator_address}")
        return

    if not utils.ask_user_confirm(f"Deploy and set validator for deal id {deal.deal_id}?", default_answer=True): return

    _ = __get_validator_address_for_deal(deal)  # just verify
    tx_hash = ValidatorFactory().create(deal.deal_id, from_private_key)

    click.echo(f"Validator deployed for deal id {deal.deal_id}: {tx_hash}")
    return tx_hash


def _deposit_and_approve_operator(deal: PoRepMarketDealProposal, from_private_key: str) -> str | None:
    from_address = w3.eth.account.from_key(from_private_key).address
    operator_approval = FileCoinPay().get_operator_approval(utils.get_env('USDC_TOKEN'),
                                                            from_address,
                                                            deal.validator_address)

    if operator_approval.is_approved:
        click.echo(f"\nOperator already approved for deal id {deal.deal_id}: {operator_approval}\n")
        return

    token_decimals = USDCToken().decimals()
    token_name = USDCToken().name()

    filecoinpay_account = FileCoinPay().get_account(utils.get_env('USDC_TOKEN'), from_address)
    filecoinpay_available_funds = filecoinpay_account.funds - filecoinpay_account.lockup_current
    filecoinpay_available_funds_tokens = utils.to_tokens(filecoinpay_available_funds, token_decimals)

    token_balance = USDCToken().balance_of(from_address)
    token_balance_tokens = utils.to_tokens(token_balance, token_decimals)

    _ = __get_validator_address_for_deal(deal)  # just verify
    permit_deadline = client_utils.get_permit_deadline()

    deposit_amount = client_utils.calculate_deposit_amount_for_deal(deal, 1)
    deposit_amount_tokens = utils.to_tokens(deposit_amount, token_decimals)

    if token_balance < deposit_amount:
        raise Exception(f"Address {from_address} {token_name} balance {token_balance_tokens} is less than required deposit {deposit_amount_tokens} for deal id {deal.deal_id}")

    # TODO verify this:
    rate_allowance = utils.MAX_UINT256
    lockup_allowance = utils.MAX_UINT256
    max_lockup_period = utils.MAX_UINT256

    # TODO deposit 0 if enough filecoinpay funds?
    if not utils.ask_user_confirm(f"Deposit {deposit_amount_tokens} {token_name} for deal id {deal.deal_id} from address {from_address} and approve operator\n"
                                  f"  Current token balance: {token_balance_tokens} {token_name}\n"
                                  f"  Current FileCoinPay account available funds: {filecoinpay_available_funds_tokens} {token_name}\n"
                                  f"  Operator address: {deal.validator_address}\n"
                                  f"  Rate allowance: {'MAX_UINT256' if rate_allowance == utils.MAX_UINT256 else rate_allowance}\n"
                                  f"  Lockup allowance: {'MAX_UINT256' if lockup_allowance == utils.MAX_UINT256 else lockup_allowance}\n"
                                  f"  Max lockup period: {'MAX_UINT256' if max_lockup_period == utils.MAX_UINT256 else max_lockup_period}"): return

    click.echo()
    signed_msg = client_utils.sign_filecoinpay_permit(deposit_amount, permit_deadline, from_private_key)
    tx_hash = FileCoinPay().deposit_with_permit_and_approve_operator(utils.get_env('USDC_TOKEN'),
                                                                     from_address,
                                                                     deposit_amount,
                                                                     permit_deadline,
                                                                     signed_msg.v, utils.int_to_bytes(signed_msg.r), utils.int_to_bytes(signed_msg.s),
                                                                     deal.validator_address,
                                                                     rate_allowance,
                                                                     lockup_allowance,
                                                                     max_lockup_period,
                                                                     from_private_key)

    click.echo(f"Deposited {deposit_amount_tokens} {token_name} and operator approved for deal id {deal.deal_id}: {tx_hash}")
    return tx_hash


def _initialize_rail(deal: PoRepMarketDealProposal, from_private_key: str) -> str | None:
    if deal.rail_id:
        click.echo(f"Rail already initialized for deal id {deal.deal_id}: {deal.rail_id}")
        return

    if not utils.ask_user_confirm(f"Initialize FileCoinPay rail for deal id {deal.deal_id}?", default_answer=True): return

    _ = __get_validator_address_for_deal(deal)  # just verify
    tx_hash = FileCoinPayValidator(deal.validator_address).create_rail(utils.get_env('USDC_TOKEN'), from_private_key)

    click.echo(f"FileCoinPay rail initialized for deal id {deal.deal_id}: {tx_hash}")
    return tx_hash
