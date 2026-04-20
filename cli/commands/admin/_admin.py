import click
from eth_account.types import PrivateKeyType
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address, ContractService

ADMIN_ADDRESS: str | None = None
ADMIN_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="Admin address to use.  [default: derived from the provided private key]")
@click.option("--private-key", envvar="ADMIN_PRIVATE_KEY", show_envvar=True, hidden=True)
@click.option("--confirm-info", is_flag=True, default=False, show_default=True,
              help="Confirm current account info before executing command.  [default: false]")
def admin(address: str | None = None, private_key: str | None = None, confirm_info: bool = False):
    """
    Admin commands for managing the PoRep Market.
    """

    global ADMIN_PRIVATE_KEY
    ADMIN_PRIVATE_KEY = private_key

    global ADMIN_ADDRESS
    ADMIN_ADDRESS = address

    if confirm_info:
        _info()
        utils.ask_user_confirm_or_fail("\n\nContinue?", default_answer=True)
        click.echo("\n\n")


# lazy initialization
def admin_address() -> Address:
    global ADMIN_ADDRESS

    if not ADMIN_ADDRESS:
        if ADMIN_PRIVATE_KEY:
            ADMIN_ADDRESS = w3.eth.account.from_key(ADMIN_PRIVATE_KEY).address
        else:
            raise Exception("Neither admin address nor private key is set")

    assert ADMIN_ADDRESS
    return Address(ADMIN_ADDRESS)


# lazy initialization
def admin_private_key() -> PrivateKeyType:
    global ADMIN_PRIVATE_KEY

    if not ADMIN_PRIVATE_KEY:
        ADMIN_PRIVATE_KEY = click.prompt("Admin private key", hide_input=True)

    commands_utils.validate_address_matches_private_key(admin_address(), ADMIN_PRIVATE_KEY)

    assert ADMIN_PRIVATE_KEY
    return ADMIN_PRIVATE_KEY


def _info():
    click.echo(f"Admin address: {ADMIN_ADDRESS if ADMIN_ADDRESS else ''}")
    click.echo(f"Admin private key: {utils.private_str_to_log_str(ADMIN_PRIVATE_KEY)}")
    click.echo()
    commands_utils.print_info()


@click.command()
@click.option("--test-keys", is_flag=True, default=False, show_default=True,
              help="Fail if the private key does not matches provided address.")
def info(test_keys: bool = False):
    """
    Display the current admin info.
    """

    if test_keys:
        _ = admin_private_key()  # validate only

    _info()


@click.command()
def wait():
    """
    Wait for all pending transactions from the current private key to be mined and exit. Useful when executing a series of commands.
    """

    ContractService.wait_for_pending_transactions(admin_address())
