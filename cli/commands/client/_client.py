import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address

CLIENT_ADDRESS: Address | None = None
CLIENT_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="Client address to use.  [default: address from private key]")
@click.option("--private-key", envvar="CLIENT_PRIVATE_KEY", show_envvar=True, help="Client private key to use.")
@click.option("--info", is_flag=True, default=False, show_default=True,
              help="Confirm current info before executing command.")
def client(address: Address | None = None, private_key: str | None = None, info: bool = False):
    """
    Client commands for interacting with the PoRep Market.
    """

    global CLIENT_PRIVATE_KEY
    CLIENT_PRIVATE_KEY = private_key

    global CLIENT_ADDRESS
    CLIENT_ADDRESS = Address(address) if address else Address(w3.eth.account.from_key(CLIENT_PRIVATE_KEY).address) if CLIENT_PRIVATE_KEY else None

    if info:
        _info()
        utils.ask_user_confirm_or_fail("\n\nContinue?", default_answer=True)
        click.echo("\n\n")


def client_address() -> Address:
    if not CLIENT_ADDRESS:
        raise Exception("Client address is not set")

    return CLIENT_ADDRESS


def client_private_key() -> str:
    commands_utils.validate_address_matches_private_key(client_address(), CLIENT_PRIVATE_KEY)

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
