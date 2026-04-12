import click

from cli import utils
from cli.services.contracts.sp_registry import SPRegistry, SPRegistryProvider


def _get_registered_sps() -> list[SPRegistryProvider]:
    return SPRegistry().get_providers_info()


@click.command()
def get_registered_sps():
    """
    Get registered SPs from the SPRegistry smart contract.
    """
    click.echo(utils.json_pretty(_get_registered_sps()))
