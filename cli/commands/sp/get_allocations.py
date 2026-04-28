import click

from cli import utils
from cli.services import rpc_utils
from cli.commands import utils as commands_utils
from cli.services import rpc_utils
from cli.services.contracts.client_contract import ClientContract
from cli.services.contracts.porep_market import PoRepMarket


@click.command()
@click.argument("deal_id", type=click.IntRange(min=0))
def get_allocations(deal_id: int):
    """
    Get client allocations for a deal.

    DEAL_ID - The id of the deal to match.
    """

    deal = PoRepMarket().get_deal_proposal(deal_id)
    manifest = commands_utils.fetch_manifest(deal.manifest_location, show_manifest=False, quiet=True)
    pieces = manifest[0]["pieces"]

    deal_allocations = ClientContract().get_client_allocation_ids_per_deal(deal_id)
    state_allocations = rpc_utils.state_get_allocations(ClientContract().actor_id())
    deal_allocations = commands_utils.match_deal_allocations(pieces, state_allocations, deal_allocations)

    click.echo(utils.json_pretty(deal_allocations))
