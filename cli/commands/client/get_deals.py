import click

from cli import utils
from cli.commands.client._client import client_address
from cli.commands.client import _utils as client_utils
from cli.services.contracts.porep_market import PoRepMarketDealState


@click.command()
@click.argument('state', required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
def get_deals(state: PoRepMarketDealState | None):
    """
    Get deals for the client by state.

    STATE - Deal state [default: all states].
    """

    click.echo(utils.json_pretty(client_utils.get_client_deals(client_address(), state)))
