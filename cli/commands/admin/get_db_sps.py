import click

from cli import utils
from cli.commands.admin import _utils as admin_utils

@click.command()
@click.option('--db-url', envvar='SP_REGISTRY_DATABASE_URL', show_envvar=True, help="SP Registry database connection string.")
@click.option('--all', is_flag=True, help="Whether to get all SPs or only KYC-approved ones (default: false).", default=False, show_default=True)
def get_db_sps(db_url: str, all: bool = False):
    """
    Get SPs from database.
    """

    result = admin_utils.get_db_sps(db_url, all)
    click.echo()
    click.echo(utils.json_pretty(result))
