import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

SP_ADDRESS: str | None = None
SP_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="SP address to use.  [default: address from private key]")
@click.option("--private-key", envvar="SP_PRIVATE_KEY", show_envvar=True, help="SP private key to use.")
@click.option("--info", is_flag=True, default=False, show_default=True,
              help="Confirm current info before executing command.")
def sp(address: str | None = None, private_key: str | None = None, info: bool = False):
    """
    Storage Provider commands for interacting with the PoRep Market.
    """

    global SP_PRIVATE_KEY
    SP_PRIVATE_KEY = private_key

    global SP_ADDRESS
    SP_ADDRESS = address

    if info:
        _info()
        utils.ask_user_confirm_or_fail("\n\nContinue?", default_answer=True)
        click.echo("\n\n")


# lazy initialization
def sp_address() -> Address:
    global SP_ADDRESS

    if not SP_ADDRESS:
        if SP_PRIVATE_KEY:
            SP_ADDRESS = w3.eth.account.from_key(SP_PRIVATE_KEY).address
        else:
            raise Exception("Neither SP address nor private key is set")

    assert SP_ADDRESS
    return Address(SP_ADDRESS)


# lazy initialization
def sp_private_key() -> str:
    commands_utils.validate_address_matches_private_key(sp_address(), SP_PRIVATE_KEY)

    assert SP_PRIVATE_KEY
    return str(SP_PRIVATE_KEY)


def _info():
    click.echo(f"SP address: {SP_ADDRESS}")
    click.echo(f"SP private key: {utils.private_str_to_log_str(SP_PRIVATE_KEY)}")
    click.echo()
    commands_utils.print_info()


@click.command()
@click.option("--test-keys", is_flag=True, default=False, show_default=True,
              help="Fail if the private key does not matches provided address.")
def info(test_keys: bool = False):
    """
    Display the current SP info.
    """

    if test_keys:
        _ = sp_private_key()  # validate only

    _info()
