import click
from web3.auto import w3

from cli import utils
from cli._cli import is_dry_run
from cli.services.contracts.contract_service import Address, ContractService
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal, PoRepMarket

# TODO LATER take sector size from smart contracts
SECTOR_SIZE_BYTES = 32 * 1024 ** 3  # 32 GiB


def bytes_to_sectors(bytes_size: int) -> float:
    return bytes_size / SECTOR_SIZE_BYTES


def get_all_deals(state: PoRepMarketDealState | str | None = None,
                  organization: Address | None = None) -> list[PoRepMarketDealProposal]:
    _state = PoRepMarketDealState.from_string(str(state)) if state else None

    if organization:
        # prefer get_deals_for_organization_by_state function when asking for organization...
        result = []
        selected_states = [_state] if _state else list(PoRepMarketDealState)

        for selected_state in selected_states:
            result.extend(PoRepMarket().get_deals_for_organization_by_state(organization, selected_state))
    else:
        # ... otherwise prefer get_all_deals function
        result = PoRepMarket().get_all_deals()

        if _state:
            result = [deal for deal in result if deal.state == _state]

    return result


def print_info():
    try:
        click.echo(f"Chain ID: {ContractService.get_chain_id()}")
    except Exception as e:
        click.echo(f"Error getting chain ID: {e}\n")

    click.echo(f"RPC_URL={utils.get_env('RPC_URL', required=False)}")
    click.echo()
    click.echo(f"POREP_MARKET={utils.get_env('POREP_MARKET', required=False)}")
    click.echo(f"CLIENT_CONTRACT={utils.get_env('CLIENT_CONTRACT', required=False)}")
    click.echo(f"SP_REGISTRY={utils.get_env('SP_REGISTRY', required=False)}")
    click.echo(f"VALIDATOR_FACTORY={utils.get_env('VALIDATOR_FACTORY', required=False)}")
    click.echo(f"FILECOIN_PAY={utils.get_env('FILECOIN_PAY', required=False)}")
    click.echo(f"USDC_TOKEN={utils.get_env('USDC_TOKEN', required=False)}")
    click.echo()
    click.echo(f"DRY_RUN={is_dry_run()}")
    click.echo(f"DEBUG={utils.get_env('DEBUG', default='False').capitalize()}")


def validate_address_matches_private_key(address: Address, private_key: str | None):
    if not private_key:
        raise Exception("Private key is not set")

    derived_address = w3.eth.account.from_key(private_key).address

    if derived_address != address:
        raise Exception(f"Address {address} does not match private key {utils.private_str_to_log_str(private_key)} (expected: {derived_address})")
