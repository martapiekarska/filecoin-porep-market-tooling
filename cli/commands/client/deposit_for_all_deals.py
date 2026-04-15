import click
from web3.auto import w3

from cli import utils
from cli.commands.client import _utils as client_utils
from cli.commands.client._client import client_private_key
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal
from cli.services.contracts.usdc_token import USDCToken


@click.command()
@click.option("--months", type=click.IntRange(min=0), default=1, show_default=True,
              help="Number of months to calculate required deposit amount for.")
def deposit_for_all_deals(months: int):
    """
    Deposit USDC funds to FileCoinPay account for all accepted deals.
    """

    _deposit_for_all_deals(months, client_private_key())


def _deposit_for_all_deals(months: int, from_private_key: str):
    from_address = w3.eth.account.from_key(from_private_key).address
    accepted_deals = client_utils.get_client_deals(from_address, PoRepMarketDealState.ACCEPTED)

    __deposit_for_all_deals(accepted_deals, months, from_private_key)


# deposits USDC funds to FileCoinPay account for X month of storing deals
def __deposit_for_all_deals(deals: list[PoRepMarketDealProposal], months: int, from_private_key: str) -> str | None:
    from_address = w3.eth.account.from_key(from_private_key).address
    filecoinpay_account = FileCoinPay().get_account(utils.get_env("USDFC_TOKEN"), from_address)

    token_decimals = USDCToken().decimals()
    token_name = USDCToken().name()

    token_balance = USDCToken().balance_of(from_address)
    token_balance_tokens = utils.to_tokens_str(token_balance, token_decimals)

    filecoinpay_available_funds = filecoinpay_account.funds - filecoinpay_account.lockup_current
    filecoinpay_available_funds_tokens = utils.to_tokens_str(filecoinpay_available_funds, token_decimals)

    total_required_amount = sum(client_utils.calculate_deposit_amount_for_deal(deal, months) for deal in deals)
    total_required_amount_tokens = utils.to_tokens_str(total_required_amount, token_decimals)

    if filecoinpay_available_funds < total_required_amount:
        deposit_amount = total_required_amount - filecoinpay_available_funds
        deposit_amount_tokens = utils.to_tokens_str(deposit_amount, token_decimals)

        permit_deadline = client_utils.get_permit_deadline()

        if token_balance < deposit_amount:
            raise Exception(
                f"Address {from_address} {token_name} balance {token_balance_tokens} {token_name} is "
                f"less than required deposit {deposit_amount_tokens} for {len(deals)} deals")

        if not utils.ask_user_confirm(
                f"\nDeposit {deposit_amount_tokens} {token_name} to FileCoinPay account for {len(deals)} deals from address {from_address}\n"
                f"  Current token balance: {token_balance_tokens} {token_name}\n"
                f"  Current FileCoinPay account available funds: {filecoinpay_available_funds_tokens} {token_name}\n"
                f"  Total required funds for {len(deals)} deals for {months} months: {total_required_amount_tokens} {token_name}"):
            return

        click.echo()
        signed_msg = client_utils.sign_filecoinpay_permit(deposit_amount, permit_deadline, from_private_key)
        tx_hash = FileCoinPay().deposit_with_permit(utils.get_env("USDFC_TOKEN"),
                                                    from_address,
                                                    deposit_amount,
                                                    permit_deadline,
                                                    signed_msg.v, utils.int_to_bytes(signed_msg.r), utils.int_to_bytes(signed_msg.s),
                                                    from_private_key)

        click.echo(f"Deposited {deposit_amount_tokens} {token_name}: {tx_hash}")
        return tx_hash
    else:
        click.echo(
            f"Existing FileCoinPay funds {filecoinpay_available_funds_tokens} {token_name} is "
            f"sufficient for total required deposit amount {total_required_amount_tokens} {token_name}")
