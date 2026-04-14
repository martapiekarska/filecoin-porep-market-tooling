import click

from web3.auto import w3
from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

SP_ADDRESS: Address | None = None
SP_PRIVATE_KEY: str | None = None


@click.group()
@click.option('--address', required=False, help="SP address to use, default is address from --private-key option.")
@click.option('--private-key', envvar='SP_PRIVATE_KEY', help="SP private key to use.", show_envvar=True)
@click.option('--debug', help="Confirm current info before executing command.", is_flag=True, default=False, show_default=True)
def sp(address: Address = None, private_key: str = None, debug: bool = False):
    """
    Storage Provider commands for interacting with the PoRep Market.
    """

    global SP_PRIVATE_KEY
    SP_PRIVATE_KEY = private_key

    global SP_ADDRESS
    SP_ADDRESS = Address(address if address else w3.eth.account.from_key(SP_PRIVATE_KEY).address)

    if debug:
        _info()
        utils.ask_user_confirm("Continue?", default_answer=True)


def sp_address() -> Address:
    if not SP_ADDRESS: raise Exception("SP address is not set")
    return SP_ADDRESS


def sp_private_key() -> str:
    if not SP_PRIVATE_KEY: raise Exception("SP private key is not set")
    return SP_PRIVATE_KEY


def _info():
    click.echo(f"SP address: {sp_address()}")
    click.echo(f"SP private key: {sp_private_key()[:6]}...{sp_private_key()[-4:]}")
    click.echo()
    commands_utils.print_info()


@click.command()
def info():
    """
    Display the current SP info.
    """

    _info()
