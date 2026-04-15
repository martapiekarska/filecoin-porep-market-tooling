import click

from cli import utils
from cli.commands.admin import _utils as admin_utils


@click.command()
@click.option("--db-url", envvar="SP_REGISTRY_DATABASE_URL", show_envvar=True, help="SP Registry database connection string.", required=True)
@click.option("--show-all", is_flag=True, help="Whether to get all SPs or only eligible for registration (default: false).", default=False, show_default=True)
@click.argument("db_id", type=click.IntRange(min=0), required=False)
def get_db_sps(db_url: str, show_all: bool = False, db_id: int | None = None):
    """
    Get SPs from SPRegistry database.

    DB_ID - ID of the Storage Provider in the SPRegistry database to fetch, default is all providers eligible for registration.
    """

    result = admin_utils.get_db_sps(db_url, kyc_status="approved" if (not show_all and not db_id) else None, provider_id=db_id)
    click.echo()
    click.echo(utils.json_pretty(result))
