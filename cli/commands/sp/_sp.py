import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

SP_ADDRESS: Address | None = None
SP_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="SP address to use, default is address from --private-key option.")
@click.option("--private-key", envvar="SP_PRIVATE_KEY", help="SP private key to use.", show_envvar=True)
@click.option("--info", help="Confirm current info before executing command.", is_flag=True, default=False, show_default=True)
def sp(address: Address = None, private_key: str = None, info: bool = False):
    """
    Storage Provider commands for interacting with the PoRep Market.
    """

    global SP_PRIVATE_KEY
    SP_PRIVATE_KEY = private_key

    global SP_ADDRESS
    SP_ADDRESS = Address(address) if address else Address(w3.eth.account.from_key(SP_PRIVATE_KEY).address) if SP_PRIVATE_KEY else None

    if info:
        _info()
        utils.ask_user_confirm("Continue?", default_answer=True)


def sp_address() -> Address:
    if not SP_ADDRESS:
        raise Exception("SP address is not set")

    return SP_ADDRESS


def sp_private_key() -> str:
    commands_utils.validate_address_matches_private_key(sp_address(), SP_PRIVATE_KEY)

    return SP_PRIVATE_KEY


def _info():
    click.echo(f"SP address: {SP_ADDRESS}")
    click.echo(f"SP private key: {utils.private_key_to_log_string(SP_PRIVATE_KEY)}")
    click.echo()
    commands_utils.print_info()


@click.command()
@click.option("--test-keys", is_flag=True, help="Fail if the private key does not matches provided address.", default=False, show_default=True)
def info(test_keys: bool = False):
    """
    Display the current SP info.
    """

    if test_keys:
        commands_utils.validate_address_matches_private_key(sp_address(), sp_private_key())

    _info()
