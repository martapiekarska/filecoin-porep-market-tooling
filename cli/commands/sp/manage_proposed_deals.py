import click
from web3.auto import w3

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_private_key
from cli.services.contracts.contract_service import ContractService


# TODO LATER print deals states at the end?
def _manage_proposed_deals(from_private_key: str, answer: str | None = None):
    # wait for pending transactions
    from_address = w3.eth.account.from_key(from_private_key).address
    _ = ContractService.get_address_nonce(from_address)

    deals = commands_utils.get_all_deals(sp_utils.PoRepMarketDealState.PROPOSED, from_address)

    click.echo(f"Found {len(deals)} proposed deals.")

    for deal in deals:
        _answer = answer if answer else utils.ask_user_string(f"\nNew deal id {deal.deal_id}: {deal} ([a]ccept/[r]eject/[S]kip)",
                                                              valid_answers=["accept", "reject", "skip", "a", "r", "s"],
                                                              default_answer="skip")

        if _answer in ["accept", "a"]:
            sp_utils.accept_deal(deal, from_private_key)

        elif _answer in ["reject", "r"]:
            sp_utils.reject_deal(deal, from_private_key)

        elif _answer in ["skip", "s"]:
            continue

        else:
            raise ValueError(f"Invalid answer: {_answer}")

    click.echo("\n\nAll done!")


@click.command()
@click.argument("action", required=False, type=click.Choice(["accept", "reject"], case_sensitive=False))
# TODO LATER can --private-key be different from --address here?
def manage_proposed_deals(action: str | None):
    """
    Interactively manage proposed deals. Either accept or reject each proposed deal manually or based on provided ACTION argument.

    ACTION - Action to perform on proposed deals.
    """

    _manage_proposed_deals(sp_private_key(), answer=action)
