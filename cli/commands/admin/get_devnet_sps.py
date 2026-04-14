import click

from cli import utils
from cli.commands.admin import _utils as admin_utils


@click.command()
def get_devnet_sps():
    """
    Testing and development purposes.
    """

    click.echo(utils.json_pretty(admin_utils.get_devnet_sps()))
