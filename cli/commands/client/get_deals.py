import click

from cli import utils
from cli.commands.client import _utils as client_utils
from cli.commands.client._client import client_address
from cli.services.contracts.porep_market import PoRepMarketDealState


@click.command()
@click.argument("state", required=False, type=click.Choice(PoRepMarketDealState.to_string_list(), case_sensitive=False))
def get_deals(state: str | None):
    """
    Get deals for the client.

    STATE - Deal state to filter by. [default: all states]
    """

    click.echo(utils.json_pretty(client_utils.get_client_deals(client_address(), PoRepMarketDealState.from_string(state))))
