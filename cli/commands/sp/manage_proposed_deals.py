import contextlib

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_private_key, sp_organization_address
from cli.services.contracts.contract_service import ContractService, Address


# TODO LATER print deals states at the end?
def _manage_proposed_deals(answer: str | None = None):
    ContractService.wait_for_pending_transactions(Address.from_private_key(sp_private_key()))
    deals = commands_utils.get_all_deals(sp_utils.PoRepMarketDealState.PROPOSED, sp_organization_address())

    click.echo(f"Found {len(deals)} proposed deals.")

    for deal in deals:
        _answer = answer if answer else utils.confirm_str(f"\nNew deal id {deal.deal_id}: {deal} ([a]ccept/[r]eject/[S]kip)",
                                                          valid_answers=["accept", "reject", "skip", "a", "r", "s"],
                                                          default_answer="skip")

        with contextlib.suppress(click.Abort, click.ClickException):
            if _answer in ["accept", "a"]:
                click.echo()
                sp_utils.accept_deal(deal)

            elif _answer in ["reject", "r"]:
                click.echo()
                sp_utils.reject_deal(deal)

            elif _answer in ["skip", "s"]:
                continue

    click.echo("\n\nAll done!")


@click.command()
@click.argument("action", required=False, type=click.Choice(["accept", "reject"], case_sensitive=False))
def manage_proposed_deals(action: str | None):
    """
    Interactively manage proposed deals. Either accept or reject each proposed deal manually or based on provided ACTION argument.

    ACTION - Action to perform on proposed deals.
    """

    _manage_proposed_deals(answer=action)
