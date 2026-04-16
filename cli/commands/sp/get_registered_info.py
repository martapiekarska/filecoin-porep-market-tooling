import click

from cli import utils
from cli.commands.sp._sp import sp_address
from cli.services.contracts.sp_registry import SPRegistry


@click.command()
@click.argument('provider_id', required=False)
def get_registered_info(provider_id: str | None = None):
    """
    Get PoRep Market registered info for the SP.

    PROVIDER_ID - Provider id to query. [default: all providers under current SP organization address]
    """

    _provider_id = utils.f0_str_id_to_int(provider_id)
    click.echo([SPRegistry().get_provider_info(_provider_id)] if _provider_id else
               SPRegistry().get_providers_info_by_organization(sp_address()))
