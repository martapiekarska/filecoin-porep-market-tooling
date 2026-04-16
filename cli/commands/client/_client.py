import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

CLIENT_ADDRESS: str | None = None
CLIENT_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="Client address to use.  [default: address from private key]")
@click.option("--private-key", envvar="CLIENT_PRIVATE_KEY", show_envvar=True, help="Client private key to use.")
@click.option("--info", is_flag=True, default=False, show_default=True,
              help="Confirm current info before executing command.")
def client(address: str | None = None, private_key: str | None = None, info: bool = False):
    """
    Client commands for interacting with the PoRep Market.
    """

    global CLIENT_PRIVATE_KEY
    CLIENT_PRIVATE_KEY = private_key

    global CLIENT_ADDRESS
    CLIENT_ADDRESS = address

    if info:
        _info()
        utils.ask_user_confirm_or_fail("\n\nContinue?", default_answer=True)
        click.echo("\n\n")


# lazy initialization
def client_address() -> Address:
    global CLIENT_ADDRESS

    if not CLIENT_ADDRESS:
        if CLIENT_PRIVATE_KEY:
            CLIENT_ADDRESS = w3.eth.account.from_key(CLIENT_PRIVATE_KEY).address
        else:
            raise Exception("Neither client address nor private key is set")

    assert CLIENT_ADDRESS
    return Address(CLIENT_ADDRESS)


# lazy initialization
def client_private_key() -> str:
    commands_utils.validate_address_matches_private_key(client_address(), CLIENT_PRIVATE_KEY)

    assert CLIENT_PRIVATE_KEY
    return str(CLIENT_PRIVATE_KEY)


def _info():
    click.echo(f"Client address: {CLIENT_ADDRESS}")
    click.echo(f"Client private key: {utils.private_str_to_log_str(CLIENT_PRIVATE_KEY)}")
    click.echo()
    commands_utils.print_info()


@click.command()
@click.option("--test-keys", is_flag=True, default=False, show_default=True,
              help="Fail if the private key does not matches provided address.")
def info(test_keys: bool = False):
    """
    Display the current client info.
    """

    if test_keys:
        _ = client_private_key()  # validate only

    _info()
