import click

from web3.auto import w3
from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

ADMIN_ADDRESS: Address | None = None
ADMIN_PRIVATE_KEY: str | None = None


@click.group()
@click.option('--address', required=False, help="Admin address to use, default is address from --private-key option.")
@click.option('--private-key', envvar='ADMIN_PRIVATE_KEY', help="Admin private key to use.", show_envvar=True)
@click.option('--debug', help="Confirm current info before executing command.", is_flag=True, default=False, show_default=True)
def admin(address: Address = None, private_key: str = None, debug: bool = False):
    """
    Admin commands for managing the PoRep Market.
    """

    global ADMIN_PRIVATE_KEY
    ADMIN_PRIVATE_KEY = private_key

    global ADMIN_ADDRESS
    ADMIN_ADDRESS = Address(address if address else w3.eth.account.from_key(ADMIN_PRIVATE_KEY).address)

    if debug:
        _info()
        utils.ask_user_confirm("Continue?", default_answer=True)


def admin_address() -> Address:
    if not ADMIN_ADDRESS: raise Exception("Admin address is not set")
    return ADMIN_ADDRESS


def admin_private_key() -> str:
    if not ADMIN_PRIVATE_KEY: raise Exception("Admin private key is not set")
    return ADMIN_PRIVATE_KEY


def _info():
    click.echo(f"Admin address: {admin_address()}")
    click.echo(f"Admin private key: {admin_private_key()[:6]}...{admin_private_key()[-4:]}")
    click.echo()
    commands_utils.print_info()


@click.command()
def info():
    """
    Display the current admin info.
    """

    _info()
