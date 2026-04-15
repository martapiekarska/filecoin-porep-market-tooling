import click

from cli import utils
from cli.commands.admin import _utils as admin_utils


@click.command()
@click.argument("db_id", type=click.IntRange(min=0), required=False)
@click.option("--db-url", envvar="SP_REGISTRY_DATABASE_URL", show_envvar=True, required=True,
              help="SPRegistry database connection string.")
@click.option("--show-all", is_flag=True, default=False, show_default=True,
              help="Whether to return SPs from all organizations or only from those eligible for registration.  [default: false]")
@click.option("--indexing-pct", type=click.IntRange(0, 100), default=0, show_default=True,
              help="IPNI indexing guarantee in percentage to return; 0 means \"don't support\".")
@click.option("--miner-id", required=False,
              help="SPRegistry database miner_id (PoRep Market SP id) to return.")
# TODO LATER add organization_address argument
def get_db_sps(db_url: str, show_all: bool = False, db_id: int | None = None, indexing_pct: int = 0, miner_id: str | None = None):
    """
    Get SPs from SPRegistry database.

    DB_ID - SPRegistry database organization id to fetch SPs from. [default: SPs from all organizations eligible for registration]
    """

    click.echo(utils.json_pretty(
        admin_utils.get_db_sps(
            db_url,
            kyc_status="approved" if (not show_all and not db_id) else None,
            organization_id=db_id,
            indexing_pct=indexing_pct,
            miner_id=utils.f0_str_id_to_int(miner_id),
        )
    ))
