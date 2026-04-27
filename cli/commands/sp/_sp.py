import click
from eth_account.types import PrivateKeyType

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address, ContractService

SP_ORGANIZATION: str | None = None
SP_PRIVATE_KEY: str | None = None


@click.group()
@click.option("--organization", envvar="SP_ORGANIZATION", show_envvar=True, help="Organization address to manage SPs from.")
@click.option("--private-key", envvar="SP_PRIVATE_KEY", hidden=True)
@click.option("--confirm-info", is_flag=True, default=False, show_default=True,
              help="Confirm current account info before executing command.  [default: false]")
def sp(private_key: str | None = None, organization: str | None = None, confirm_info: bool = False):
    """
    Storage Provider commands for interacting with the PoRep Market.
    """

    global SP_PRIVATE_KEY
    SP_PRIVATE_KEY = private_key

    global SP_ORGANIZATION
    SP_ORGANIZATION = organization

    if confirm_info:
        _info()
        click.confirm("\n\nContinue?", default=True, abort=True)
        click.echo("\n\n")


def sp_organization_address() -> Address:
    if not SP_ORGANIZATION:
        raise click.ClickException("SP organization is not set")

    return Address(SP_ORGANIZATION)


# returns SP's wallet address which might be different that sp_organization()
def sp_address() -> Address:
    return Address.from_private_key(sp_private_key())


# lazy initialization
def sp_private_key() -> PrivateKeyType:
    global SP_PRIVATE_KEY

    if not SP_PRIVATE_KEY:
        SP_PRIVATE_KEY = click.prompt("SP private key", hide_input=True)

    assert SP_PRIVATE_KEY
    return SP_PRIVATE_KEY


def _info():
    click.echo(f"SP organization: {SP_ORGANIZATION if SP_ORGANIZATION else ''}")
    click.echo(f"SP organization address: {sp_organization_address() if SP_ORGANIZATION else ''}")
    click.echo(f"SP wallet address: {sp_address() if SP_PRIVATE_KEY else ''}")
    click.echo(f"SP wallet private key: {utils.private_str_to_log_str(SP_PRIVATE_KEY)}")
    click.echo()
    commands_utils.print_info()


@click.command()
def info():
    """
    Display the current SP info.
    """

    _info()


@click.command()
def wait():
    """
    Wait for all pending transactions from the current private key to be mined and exit. Useful when executing a series of commands.
    """

    ContractService.wait_for_pending_transactions(sp_address())
