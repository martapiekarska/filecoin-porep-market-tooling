import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket


@click.command()
@click.argument("state", required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
@click.option("--deal-id", required=False, type=click.IntRange(min=0), help="Deal id to fetch.")
def get_deals(state: str | None, deal_id: int | None = None):
    """
    Get all deals.

    STATE - Deal state to filter by.
    """

    _state = PoRepMarketDealState.from_string(state)

    if deal_id is not None:
        deal = PoRepMarket().get_deal_proposal(deal_id)
        result = [deal] if deal and (_state is None or deal.state == _state) else []
    else:
        result = commands_utils.get_all_deals(_state)

    click.echo(utils.json_pretty(result))
