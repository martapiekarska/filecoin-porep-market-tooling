import click

from cli import utils
from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_address
from cli.services.contracts.porep_market import PoRepMarketDealState
from cli.services.contracts.sp_registry import SPRegistry


@click.command()
@click.argument("state", required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
@click.option("--provider-id", required=False,
              help="Provider id to filter deals by.  [default: all providers under current SP organization address]")
def get_deals(state: PoRepMarketDealState | None = None, provider_id: str | None = None):
    """
    Get deals for the current SP.

    STATE - Deal state to filter by. [default: all states]
    """

    _provider_id = utils.f0_str_id_to_int(provider_id) if provider_id else None

    if _provider_id:
        provider_info = SPRegistry().get_provider_info(_provider_id)
        organization_address = provider_info.organization_address
    else:
        organization_address = sp_address()

    result = sp_utils.get_organization_deals(state, organization_address)

    if _provider_id:
        result = [deal for deal in result if deal.provider_id == _provider_id]

    click.echo(utils.json_pretty(result))
