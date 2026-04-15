import click

from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_private_key


@click.command()
@click.argument('deal_id', type=click.INT)
def accept_deal(deal_id: int):
    """
    Accept a deal proposal.

    DEAL_ID - The id of the deal proposal to accept.
    """

    sp_utils.accept_deal_id(deal_id, sp_private_key())
