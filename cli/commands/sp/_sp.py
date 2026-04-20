import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address, ContractService

SP_ADDRESS: str | None = None
SP_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--address", help="SP address to use.  [default: address from the private key]")
@click.option("--private-key", envvar="SP_PRIVATE_KEY", show_envvar=True, hidden=True)
@click.option("--confirm-info", is_flag=True, default=False, show_default=True, help="Confirm current account info before executing command.")
def sp(address: str | None = None, private_key: str | None = None, confirm_info: bool = False):
    """
    Storage Provider commands for interacting with the PoRep Market.
    """

    if private_key:
        click.echo("Be aware that when using the [--private-key] option, the private key may be visible in the command history or process list.\n"
                   "This is a default system behavior and is not specific to this app.\n"
                   "Refer to README to learn more.\n")

    global SP_PRIVATE_KEY
    SP_PRIVATE_KEY = private_key

    global SP_ADDRESS
    SP_ADDRESS = address

    if confirm_info:
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
    global SP_PRIVATE_KEY

    if not SP_PRIVATE_KEY:
        SP_PRIVATE_KEY = click.prompt("SP private key", hide_input=True)

    commands_utils.validate_address_matches_private_key(sp_address(), SP_PRIVATE_KEY)

    assert SP_PRIVATE_KEY
    return str(SP_PRIVATE_KEY)


def _info():
    click.echo(f"SP address: {SP_ADDRESS if SP_ADDRESS else ''}")
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


@click.command()
def wait():
    """
    Wait for all pending transactions from the current private key to be mined and exit. Useful when executing a series of commands.
    """

    # wait for pending transactions
    _ = ContractService.get_address_nonce(sp_address())
