import click

from cli.commands import utils as commands_utils


@click.command()
def info():
    """
    Display the current info.
    """

    commands_utils.print_info()
