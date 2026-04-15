import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market import PoRepMarketDealState


@click.command()
@click.argument('state', required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
def get_deals(state: PoRepMarketDealState | None):
    """
    Get all deals by STATE.

    STATE - Deal state [default: all states].
    """

    click.echo(utils.json_pretty(commands_utils.get_all_deals(state)))
