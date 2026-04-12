import click

from cli.commands.admin._admin import admin_private_key
from cli.commands.admin import _utils as admin_utils
from cli.services.contracts.sp_registry import SPRegistry, SPRegistryProvider
from cli import utils


def _register_sps(providers: list[SPRegistryProvider], from_private_key: str):
    for provider in providers:
        is_registered = SPRegistry().is_provider_registered(provider.provider_id)

        if is_registered:
            registered_info = SPRegistry().get_provider_info(provider.provider_id)
            different_parameters = {k: {'new': v, 'old': getattr(registered_info, k)} for k, v in provider.__dict__.items() if getattr(registered_info, k) != getattr(provider, k)}

            if not different_parameters:
                click.echo(f"Provider {provider.provider_id} already registered with same parameters, skipping...")
                continue
            else:
                if not utils.ask_user_confirm(f"\nProvider {provider.provider_id} already registered with different parameters\n"
                                              f"Do you want to update provider {provider.provider_id} parameters?\n"
                                              f"{utils.json_pretty(different_parameters)}"): continue

                if provider.max_deal_duration_days != registered_info.max_deal_duration_days or provider.min_deal_duration_days != registered_info.min_deal_duration_days:
                    _different_parameters = {k: v for k, v in different_parameters.items() if k in ['max_deal_duration_days', 'min_deal_duration_days']}
                    if not utils.ask_user_confirm(f"Updating (max_deal_duration_days, min_deal_duration_days) for provider {provider.provider_id}: {_different_parameters}",
                                                  default_answer=True): continue

                    tx_hash = SPRegistry().set_deal_duration_limits(provider.provider_id, provider.min_deal_duration_days, provider.max_deal_duration_days, from_private_key)
                    click.echo(f"Updated deal duration limits for provider {provider.provider_id}: {tx_hash}")

                if provider.price_per_sector_per_month != registered_info.price_per_sector_per_month:
                    if not utils.ask_user_confirm(f"Updating price_per_sector_per_month for provider {provider.provider_id}: {different_parameters['price_per_sector_per_month']}",
                                                  default_answer=True): continue

                    tx_hash = SPRegistry().set_price(provider.provider_id, provider.price_per_sector_per_month, from_private_key)
                    click.echo(f"Updated price per sector per month for provider {provider.provider_id}: {tx_hash}")

                if provider.capabilities != registered_info.capabilities:
                    if not utils.ask_user_confirm(f"\nUpdating capabilities for provider {provider.provider_id}: {different_parameters['capabilities']}", default_answer=True): continue

                    tx_hash = SPRegistry().set_capabilities(provider.provider_id,
                                                            provider.capabilities,
                                                            from_private_key)
                    click.echo(f"Updated capabilities for provider {provider.provider_id}: {tx_hash}")

                if provider.payee_address != registered_info.payee_address:
                    if not utils.ask_user_confirm(f"Updating payee_address for provider {provider.provider_id}: {different_parameters['payee_address']}", default_answer=True): continue

                    tx_hash = SPRegistry().set_payee(provider.provider_id, provider.payee_address, from_private_key)
                    click.echo(f"Updated payee address for provider {provider.provider_id}: {tx_hash}")

                if provider.available_bytes != registered_info.available_bytes:
                    if not utils.ask_user_confirm(f"Updating available_bytes for provider {provider.provider_id}: {different_parameters['available_bytes']}",
                                                  default_answer=True): continue

                    tx_hash = SPRegistry().update_available_space(provider.provider_id, provider.available_bytes, from_private_key)
                    click.echo(f"Updated available bytes for provider {provider.provider_id}: {tx_hash}")

                if provider.organization_address != registered_info.organization_address:
                    click.echo(f"Different organization_address for provider {provider.provider_id} cannot be updated: {different_parameters['organization_address']}")

        else:
            if not utils.ask_user_confirm(f"\nRegistering Storage Provider with parameters: {provider}", default_answer=True): continue

            tx_hash = SPRegistry().register_provider_for(provider, from_private_key)
            click.echo(f"Provider {provider.provider_id} registered: {tx_hash}")


@click.command()
@click.option('--db-url', envvar='SP_REGISTRY_DATABASE_URL', show_envvar=True, help="SP Registry database connection string.")
def register_db_sps(db_url: str):
    """
    Register Storage Providers from DB at DB_URL.

    DB_URL - database connection URL, default is env SP_REGISTRY_DATABASE_URL.
    """
    _register_sps(admin_utils.get_db_sps(db_url), admin_private_key())


@click.command()
def register_devnet_sps():
    """
    Testing and development purposes.
    """
    _register_sps(admin_utils.get_devnet_sps(), admin_private_key())
