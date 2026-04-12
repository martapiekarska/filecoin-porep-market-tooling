import click

from web3 import Web3
from cli import utils
from cli._cli import is_dry_run
from cli.services.contracts.contract_service import Address
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal, PoRepMarket
from cli.services.contracts.sp_registry import SPRegistry


def get_all_deals(state: PoRepMarketDealState = None, organization: Address = None) -> list[PoRepMarketDealProposal]:
    states = [PoRepMarketDealState.from_string(str(state))] if state else list(PoRepMarketDealState)
    organizations = [organization] if organization else list(set([provider.organization_address for provider in SPRegistry().get_providers_info()]))

    deals: list[PoRepMarketDealProposal] = []

    for _organization in organizations:
        for state in states:
            deals.extend(PoRepMarket().get_deals_for_organization_by_state(_organization, state))

    return deals

def get_chain_id() -> int:
    return Web3(Web3.HTTPProvider(utils.get_env('RPC_URL'))).eth.chain_id

def print_info():
    click.echo(f"Chain ID: {get_chain_id()}")
    click.echo(f"RPC_URL={utils.get_env('RPC_URL')}")
    click.echo()
    click.echo(f"POREP_MARKET={utils.get_env('POREP_MARKET')}")
    click.echo(f"CLIENT_CONTRACT={utils.get_env('CLIENT_CONTRACT')}")
    click.echo(f"SP_REGISTRY={utils.get_env('SP_REGISTRY')}")
    click.echo(f"VALIDATOR_FACTORY={utils.get_env('VALIDATOR_FACTORY')}")
    click.echo(f"FILECOIN_PAY={utils.get_env('FILECOIN_PAY')}")
    click.echo(f"USDC_TOKEN={utils.get_env('USDC_TOKEN')}")
    click.echo()
    click.echo(f"DRY_RUN={is_dry_run()}")
    click.echo(f"DEBUG={utils.get_env('DEBUG', default='False').capitalize()}")
