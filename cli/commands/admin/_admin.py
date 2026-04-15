import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

ADMIN_ADDRESS: Address | None = None
ADMIN_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="Admin address to use, default is address from --private-key option.")
@click.option("--private-key", envvar="ADMIN_PRIVATE_KEY", help="Admin private key to use.", show_envvar=True)
@click.option("--info", help="Confirm current info before executing command.", is_flag=True, default=False, show_default=True)
def admin(address: Address = None, private_key: str = None, info: bool = False):
    """
    Admin commands for managing the PoRep Market.
    """

    global ADMIN_PRIVATE_KEY
    ADMIN_PRIVATE_KEY = private_key

    global ADMIN_ADDRESS
    ADMIN_ADDRESS = Address(address) if address else Address(w3.eth.account.from_key(ADMIN_PRIVATE_KEY).address) if ADMIN_PRIVATE_KEY else None

    if info:
        _info()
        utils.ask_user_confirm("Continue?", default_answer=True)


def admin_address() -> Address:
    if not ADMIN_ADDRESS:
        raise Exception("Admin address is not set")

    return ADMIN_ADDRESS


def admin_private_key() -> str:
    commands_utils.validate_address_matches_private_key(admin_address(), ADMIN_PRIVATE_KEY)

    return ADMIN_PRIVATE_KEY


def _info():
    click.echo(f"Admin address: {ADMIN_ADDRESS}")
    click.echo(f"Admin private key: {utils.private_key_to_log_string(ADMIN_PRIVATE_KEY)}")
    click.echo()
    commands_utils.print_info()


@click.command()
@click.option("--test-keys", is_flag=True, help="Fail if the private key does not matches provided address.", default=False, show_default=True)
def info(test_keys: bool = False):
    """
    Display the current admin info.
    """

    if test_keys:
        commands_utils.validate_address_matches_private_key(admin_address(), admin_private_key())

    _info()
