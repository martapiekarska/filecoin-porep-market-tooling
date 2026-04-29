import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.client_contract import ClientContract
from cli.services.contracts.porep_market import PoRepMarket
from cli.services.web3_service import Web3Service


@click.command()
@click.argument("deal_id", type=click.IntRange(min=0))
def get_allocations(deal_id: int):
    """
    Get client allocations for a deal.

    DEAL_ID - The id of the deal to get allocations for.
    """

    deal = PoRepMarket().get_deal_proposal(deal_id)
    manifest = commands_utils.fetch_manifest(deal.manifest_location, show_manifest=False, quiet=True)
    pieces = manifest[0]["pieces"]

    deal_allocations = ClientContract().get_client_allocation_ids_per_deal(deal_id)
    state_allocations = Web3Service().state_get_allocations(ClientContract().address().to_actor_id())
    deal_allocations = commands_utils.match_deal_allocations(pieces, state_allocations, deal_allocations)

    click.echo(utils.json_pretty(deal_allocations))
