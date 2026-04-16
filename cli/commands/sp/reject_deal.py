import click

from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_private_key, sp_address
from cli.services.contracts.contract_service import ContractService


@click.command()
@click.argument('deal_id', type=click.INT)
# TODO LATER print deal state at the end?
def reject_deal(deal_id: int):
    """
    Reject a deal proposal.

    DEAL_ID - The id of the deal proposal to reject.
    """

    # wait for pending transactions
    _ = ContractService.get_address_nonce(sp_address())

    sp_utils.reject_deal_id(deal_id, sp_private_key())
