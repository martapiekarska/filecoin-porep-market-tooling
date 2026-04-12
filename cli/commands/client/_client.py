import click

from web3.auto import w3
from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

CLIENT_ADDRESS: Address | None = None
CLIENT_PRIVATE_KEY: str | None = None


@click.group()
@click.option('--address', required=False, help="Client address to use, default is address from --private-key option.")
@click.option('--private-key', envvar='CLIENT_PRIVATE_KEY', help="Client private key to use.", show_envvar=True)
@click.option('--debug', help="Confirm current info before executing command.", is_flag=True, default=False, show_default=True)
def client(address: Address = None, private_key: str = None, debug: bool = False):
    """
    Client commands for interacting with the PoRep Market.
    """
    global CLIENT_PRIVATE_KEY
    CLIENT_PRIVATE_KEY = private_key

    global CLIENT_ADDRESS
    CLIENT_ADDRESS = Address(address if address else w3.eth.account.from_key(CLIENT_PRIVATE_KEY).address)

    if debug:
        _info()
        utils.ask_user_confirm("Continue?", default_answer=True)


def client_address() -> Address:
    if not CLIENT_ADDRESS: raise Exception("Client address is not set")
    return CLIENT_ADDRESS


def client_private_key() -> str:
    if not CLIENT_PRIVATE_KEY: raise Exception("Client private key is not set")
    return CLIENT_PRIVATE_KEY


def _info():
    click.echo(f"Client address: {client_address()}")
    click.echo(f"Client private key: {client_private_key()[:6]}...{client_private_key()[-4:]}")
    click.echo()
    commands_utils.print_info()


@click.command()
def info():
    """
    Display the current client info.
    """
    _info()
