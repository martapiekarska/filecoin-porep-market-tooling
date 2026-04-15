import click

from cli import utils
from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_address
from cli.services.contracts.porep_market import PoRepMarketDealState


@click.command()
@click.argument('state', required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
def get_deals(state: PoRepMarketDealState | None):
    """
    Get all deals by STATE.

    STATE - Deal state [default: all states].
    """

    click.echo(utils.json_pretty(sp_utils.get_sp_deals(state, sp_address())))
