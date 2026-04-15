import click

from cli import utils
from cli.commands.client._client import client_address
from cli.services.contracts.contract_service import Address
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.filecoin_pay import FileCoinPay


def _get_filecoin_pay_account(owner_address: Address, token_address: Address):
    token_contract = ERC20Contract(token_address)
    account = FileCoinPay().get_account(token_address, owner_address)

    return {
        "owner": str(owner_address),
        "token": token_address,
        "token_name": token_contract.name(),
        "funds_tokens": utils.to_tokens(account.funds, token_contract.decimals()),
        "account": account.__dict__
    }


@click.command()
@click.option("--token-address", envvar="USDC_TOKEN", show_envvar=True, help="ERC20 token address to ask for.", required=True)
def get_filecoin_pay_account(token_address: Address):
    """
    Get client's FileCoinPay account for the organization and token address.
    Note: PoRep market currently supports USDC only.
    """

    click.echo(utils.json_pretty(_get_filecoin_pay_account(client_address(), token_address)))
