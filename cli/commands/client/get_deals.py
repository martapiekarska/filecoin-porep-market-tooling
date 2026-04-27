import click

from cli import utils
from cli.commands.client import _utils as client_utils
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarket


@click.command()
@click.argument("state", required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
@click.option("--deal-id", required=False, type=click.IntRange(min=0), help="Deal id to fetch.")
def get_deals(state: str | None, deal_id: int | None = None):
    """
    Get deals for the client.

    STATE - Deal state to filter by.
    """

    if deal_id is not None:
        result = [PoRepMarket().get_deal_proposal(deal_id)]
    else:
        result = client_utils.get_client_deals(PoRepMarketDealState.from_string(state))

    click.echo(utils.json_pretty(result))
