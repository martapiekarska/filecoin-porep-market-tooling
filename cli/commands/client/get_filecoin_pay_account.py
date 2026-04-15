import click

from cli import utils
from cli.commands.client._client import client_address
from cli.services.contracts.contract_service import Address
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.filecoin_pay import FileCoinPay


@click.command()
@click.option("--token-address", envvar="USDFC_TOKEN", show_envvar=True, required=True,
              help="ERC20 token address to ask for.")
def get_filecoin_pay_account(token_address: Address):
    """
    Get client's FileCoinPay account for the organization and token address.
    Note: PoRep Market currently supports USDC only.
    """

    token_contract = ERC20Contract(token_address)
    account = FileCoinPay().get_account(token_address, client_address())

    click.echo(utils.json_pretty({
        "owner": str(client_address()),
        "token": token_address,
        "funds": f"{utils.to_tokens_str(account.funds, token_contract.decimals())} {token_contract.name()}",
        "account": account.__dict__
    }
    ))
