import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket


@click.command()
@click.argument('state', required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
@click.option("--deal-id", required=False, type=click.IntRange(min=0),
              help="Deal id to fetch.  [default: all deals]")
def get_deals(state: PoRepMarketDealState | None, deal_id: int | None = None):
    """
    Get all deals.

    STATE - Deal state to filter by. [default: all states]
    """

    if deal_id is not None:
        result = [PoRepMarket().get_deal_proposal(deal_id)]
        if state:
            result = [deal for deal in result if deal.state == state]
    else:
        result = commands_utils.get_all_deals(state)

    click.echo(utils.json_pretty(result))
