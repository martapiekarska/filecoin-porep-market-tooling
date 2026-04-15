import click
from web3 import Web3
from web3.auto import w3

from cli import utils
from cli._cli import is_dry_run
from cli.services.contracts.contract_service import Address
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal, PoRepMarket
from cli.services.contracts.sp_registry import SPRegistry

# TODO LATER take sector size from smart contracts
SECTOR_SIZE_BYTES = 32 * 1024 ** 3  # 32 GiB


def bytes_to_sectors(bytes_size: int) -> float:
    return bytes_size / SECTOR_SIZE_BYTES


def get_all_deals(state: PoRepMarketDealState | None = None, organization: Address | None = None) -> list[PoRepMarketDealProposal]:
    states = [PoRepMarketDealState.from_string(str(state))] if state else list(PoRepMarketDealState)
    organizations = [organization] if organization else list(set([provider.organization_address for provider in SPRegistry().get_providers_info()]))

    deals: list[PoRepMarketDealProposal] = []

    for _organization in organizations:
        for _state in states:
            deals.extend(PoRepMarket().get_deals_for_organization_by_state(_organization, _state))

    return deals


def get_chain_id() -> int:
    return Web3(Web3.HTTPProvider(utils.get_env("RPC_URL"))).eth.chain_id


def print_info():
    try:
        click.echo(f"Chain ID: {get_chain_id()}")
    except Exception as e:
        click.echo(f"Error getting chain ID: {e}\n")

    click.echo(f"RPC_URL={utils.get_env('RPC_URL', required=False)}")
    click.echo()
    click.echo(f"POREP_MARKET={utils.get_env('POREP_MARKET', required=False)}")
    click.echo(f"CLIENT_CONTRACT={utils.get_env('CLIENT_CONTRACT', required=False)}")
    click.echo(f"SP_REGISTRY={utils.get_env('SP_REGISTRY', required=False)}")
    click.echo(f"VALIDATOR_FACTORY={utils.get_env('VALIDATOR_FACTORY', required=False)}")
    click.echo(f"FILECOIN_PAY={utils.get_env('FILECOIN_PAY', required=False)}")
    click.echo(f"USDFC_TOKEN={utils.get_env('USDFC_TOKEN', required=False)}")
    click.echo()
    click.echo(f"DRY_RUN={is_dry_run()}")
    click.echo(f"DEBUG={utils.get_env('DEBUG', default='False').capitalize()}")


def validate_address_matches_private_key(address: Address, private_key: str | None):
    if not private_key:
        raise Exception("Private key is not set")

    derived_address = w3.eth.account.from_key(private_key).address

    if derived_address != address:
        raise Exception(f"Address {address} does not match private key {utils.private_str_to_log_str(private_key)} (expected: {derived_address})")
