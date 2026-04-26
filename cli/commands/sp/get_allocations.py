from typing import Dict

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts import rpc_utils
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

    client_contract = ClientContract()
    client_allocations = client_contract.get_client_allocation_ids_per_deal(deal_id)
    state_allocations = rpc_utils.state_get_allocations(client_contract.actor_id())
    aggregated_allocations = aggregate_allocations(state_allocations, client_allocations, pieces)

    click.echo(utils.json_pretty(aggregated_allocations))


def aggregate_allocations(state_allocations: Dict[str, dict], client_allocations: list[int], pieces: list[dict]) -> list[dict]:
    manifest_cids = {p["pieceCid"] for p in pieces}

    return [
        {"allocationId": alloc_id, "CID": state_allocations[str(alloc_id)].get("Data", {}).get("/")}
        for alloc_id in client_allocations
        if str(alloc_id) in state_allocations and state_allocations[str(alloc_id)].get("Data", {}).get("/") in manifest_cids
    ]
