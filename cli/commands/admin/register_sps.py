import click
from web3.auto import w3

from cli import utils
from cli.commands.admin import _utils as admin_utils
from cli.commands.admin._admin import admin_private_key
from cli.services.contracts.contract_service import ContractService
from cli.services.contracts.sp_registry import SPRegistry, SPRegistryProvider


def __update_provider_params(provider: SPRegistryProvider,
                             registered_info: SPRegistryProvider,
                             different_parameters: dict,
                             from_private_key: str):
    #
    if provider.organization_address != registered_info.organization_address:
        raise Exception(f"Organization address cannot be updated for provider {utils.int_id_to_f0_str(provider.provider_id)}")

    if (provider.max_deal_duration_days, provider.min_deal_duration_days) != (registered_info.max_deal_duration_days, registered_info.min_deal_duration_days):
        _different_parameters = {k: v for k, v in different_parameters.items() if k in ["max_deal_duration_days", "min_deal_duration_days"]}

        if utils.ask_user_confirm(
                f"Updating (max_deal_duration_days, min_deal_duration_days) for provider {utils.int_id_to_f0_str(provider.provider_id)}: "
                f"{_different_parameters}",
                default_answer=True):
            #
            tx_hash = SPRegistry().set_deal_duration_limits(provider.provider_id,
                                                            provider.min_deal_duration_days,
                                                            provider.max_deal_duration_days,
                                                            from_private_key)

            click.echo(f"Updated deal duration limits for provider {utils.int_id_to_f0_str(provider.provider_id)}: {tx_hash}")

        else:
            click.echo("Skipped this parameter\n")

    if provider.price_per_sector_per_month != registered_info.price_per_sector_per_month:
        if utils.ask_user_confirm(
                f"Updating price_per_sector_per_month for provider {utils.int_id_to_f0_str(provider.provider_id)}: "
                f"{different_parameters['price_per_sector_per_month']}",
                default_answer=True):
            #
            tx_hash = SPRegistry().set_price(provider.provider_id,
                                             provider.price_per_sector_per_month,
                                             from_private_key)

            click.echo(f"Updated price per sector per month for provider {utils.int_id_to_f0_str(provider.provider_id)}: {tx_hash}")

        else:
            click.echo("Skipped this parameter\n")

    if provider.capabilities != registered_info.capabilities:
        if utils.ask_user_confirm(
                f"\nUpdating capabilities for provider {utils.int_id_to_f0_str(provider.provider_id)}: "
                f"{different_parameters['capabilities']}",
                default_answer=True):
            #
            tx_hash = SPRegistry().set_capabilities(provider.provider_id,
                                                    provider.capabilities,
                                                    from_private_key)

            click.echo(f"Updated capabilities for provider {utils.int_id_to_f0_str(provider.provider_id)}: {tx_hash}")

        else:
            click.echo("Skipped this parameter\n")

    if provider.payee_address != registered_info.payee_address:
        if utils.ask_user_confirm(
                f"Updating payee_address for provider {utils.int_id_to_f0_str(provider.provider_id)}: "
                f"{different_parameters['payee_address']}",
                default_answer=True):
            #
            tx_hash = SPRegistry().set_payee(provider.provider_id,
                                             provider.payee_address,
                                             from_private_key)

            click.echo(f"Updated payee address for provider {utils.int_id_to_f0_str(provider.provider_id)}: {tx_hash}")

        else:
            click.echo("Skipped this parameter\n")

    if provider.available_bytes != registered_info.available_bytes:
        if utils.ask_user_confirm(
                f"Updating available_bytes for provider {utils.int_id_to_f0_str(provider.provider_id)}: "
                f"{different_parameters['available_bytes']}",
                default_answer=True):
            #
            tx_hash = SPRegistry().update_available_space(provider.provider_id,
                                                          provider.available_bytes,
                                                          from_private_key)

            click.echo(f"Updated available bytes for provider {utils.int_id_to_f0_str(provider.provider_id)}: {tx_hash}")

        else:
            click.echo("Skipped this parameter\n")


# TODO LATER print register provider at the end?
def _register_sps(providers: list[SPRegistryProvider], from_private_key: str):
    # wait for pending transactions
    _ = ContractService.get_address_nonce(w3.eth.account.from_key(from_private_key).address)

    for provider in providers:
        is_registered = SPRegistry().is_provider_registered(provider.provider_id)

        if is_registered:
            # update provider parameters if different from registered ones

            registered_info = SPRegistry().get_provider_info(provider.provider_id)
            different_parameters = {k: {"new": v, "old": getattr(registered_info, k)}
                                    for k, v in provider.__dict__.items() if
                                    getattr(registered_info, k) != getattr(provider, k)}

            if not different_parameters:
                click.echo(f"Provider {utils.int_id_to_f0_str(provider.provider_id)} already registered with same parameters, skipping...")
                continue

            if provider.organization_address != registered_info.organization_address:
                click.echo(
                    f"\nCannot update provider info: different organization_address for provider {utils.int_id_to_f0_str(provider.provider_id)}: "
                    f"{different_parameters['organization_address']}")
                #
                continue

            if not utils.ask_user_confirm(f"\nProvider {utils.int_id_to_f0_str(provider.provider_id)} already registered with different parameters\n"
                                          f"Do you want to update provider {utils.int_id_to_f0_str(provider.provider_id)} parameters?\n"
                                          f"{utils.json_pretty(different_parameters)}"):
                #
                click.echo("Skipped this provider")
                continue

            __update_provider_params(provider, registered_info, different_parameters, from_private_key)

        else:
            # register provider with given parameters

            if not utils.ask_user_confirm(f"\nRegistering Storage Provider with parameters: {provider}", default_answer=True):
                click.echo("Skipped this provider")
                continue

            if not utils.ask_user_confirm(f"\nThe organization_address {provider.organization_address} cannot be changed "
                                          f"once registered for provider_id {utils.int_id_to_f0_str(provider.provider_id)}. Are you sure this is correct?",
                                          default_answer=False):
                click.echo("Skipped this provider")
                continue

            tx_hash = SPRegistry().register_provider_for(provider, from_private_key)
            click.echo(f"Provider {utils.int_id_to_f0_str(provider.provider_id)} registered: {tx_hash}")


@click.command()
@click.argument("db_id", type=click.IntRange(min=0), required=False)
@click.option("--db-url", envvar="SP_REGISTRY_DATABASE_URL", show_envvar=True, required=True,
              help="SPRegistry database connection string.")
@click.option("--indexing-pct", type=click.IntRange(0, 100), default=0, show_default=True,
              help="IPNI indexing guarantee in percentage to use; 0 means \"don't support\".", )
@click.option("--miner-id", required=False,
              help="SPRegistry database miner_id (PoRep Market SP ID) to register.")
# TODO LATER add organization_address argument
def register_db_sps(db_url: str, db_id: int | None = None, indexing_pct: int = 0, miner_id: str | None = None):
    """
    Interactively register SPs from SPRegistry database.

    \b
    1. Fetch and print SPs from SPRegistry database,
    2. register them one by one on-chain via SPRegistry contract.

    DB_ID - SPRegistry database organization id to register SPs from. [default: SPs from all organizations eligible for registration]
    """

    _register_sps(
        admin_utils.get_db_sps(db_url,
                               kyc_status="approved",
                               organization_id=db_id,
                               indexing_pct=indexing_pct,
                               miner_id=utils.f0_str_id_to_int(miner_id)),
        admin_private_key())


@click.command()
def register_devnet_sps():
    """
    Testing and development purposes.
    """

    _register_sps(admin_utils.get_devnet_sps(), admin_private_key())
