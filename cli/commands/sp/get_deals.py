import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.sp._sp import sp_address
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket
from cli.services.contracts.sp_registry import SPRegistry


@click.command()
@click.argument("state", required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
@click.option("--provider-id", required=False, help="Provider id to filter deals by.")
@click.option("--deal-id", required=False, type=click.IntRange(min=0), help="Deal id to fetch.")
def get_deals(state: str | None = None, provider_id: str | None = None, deal_id: int | None = None):
    """
    Get deals for the current SP.

    STATE - Deal state to filter by.
    """

    if deal_id is not None:
        _result = PoRepMarket().get_deal_proposal(deal_id)

        if not _result:
            raise Exception(f"Deal id {deal_id} not found")

        result = [_result]
    else:
        _state = PoRepMarketDealState.from_string(state)
        _provider_id = utils.f0_str_id_to_int(provider_id) if provider_id else None

        if _provider_id:
            provider_info = SPRegistry().get_provider_info(_provider_id)

            if not provider_info:
                raise Exception(f"Provider {_provider_id} not found")

            organization_address = provider_info.organization_address
        else:
            organization_address = sp_address()

        result = commands_utils.get_all_deals(_state, organization_address)

        if _provider_id:
            result = [deal for deal in result if deal.provider_id == _provider_id]

    click.echo(utils.json_pretty(result))
