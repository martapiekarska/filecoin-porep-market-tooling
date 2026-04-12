import click

from cli import utils
from cli.commands.sp import _utils as sp_utils
from cli.commands.sp._sp import sp_private_key
from web3.auto import w3


def _manage_proposed_deals(from_private_key: str, answer: str | None = None):
    from_address = w3.eth.account.from_key(from_private_key).address
    deals = sp_utils.get_sp_deals(sp_utils.PoRepMarketDealState.Proposed, from_address)

    click.echo(f"Found {len(deals)} proposed deals.")

    for deal in deals:
        _answer = answer if answer else utils.ask_user_string(f"\nNew deal id {deal.deal_id}: {deal} ([a]ccept/[r]eject/[S]kip)",
                                                              valid_values=['accept', 'reject', 'skip', 'a', 'r', 's'],
                                                              default_value='skip')

        if _answer in ['accept', 'a']:
            sp_utils.accept_deal_id(deal.deal_id, from_private_key)

        elif _answer in ['reject', 'r']:
            sp_utils.reject_deal_id(deal.deal_id, from_private_key)

        elif _answer in ['skip', 's']:
             continue

        else:
            raise ValueError(f"Invalid answer: {_answer}")


@click.command()
@click.argument('action', required=False, type=click.Choice(['accept', 'reject'], case_sensitive=False))
def manage_proposed_deals(action: str | None):
    """
    \b
    Interactively manage proposed deals.
    Either accept/reject each proposed deal manually or based on provided ACTION argument.
    All write operations requires confirmation before sending.

    ACTION - Action to perform on proposed deals.
    """

    _manage_proposed_deals(sp_private_key(), answer=action)
