import click

from cli import utils
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal, PoRepMarket


def accept_deal(deal: PoRepMarketDealProposal, from_private_key: str) -> str | None:
    if deal.state != PoRepMarketDealState.PROPOSED:
        click.echo(f"Deal id {deal.deal_id} is not in Proposed state, current state: {deal.state}")
        return

    if not utils.ask_user_confirm(f"\nAccepting deal id {deal.deal_id}: {deal}"):
        click.echo("Canceled!\n")
        return

    tx_hash = PoRepMarket().accept_deal(deal.deal_id, from_private_key)
    click.echo(f"Deal id {deal.deal_id} accepted: {tx_hash}")
    return tx_hash


def reject_deal(deal: PoRepMarketDealProposal, from_private_key: str) -> str | None:
    if deal.state != PoRepMarketDealState.PROPOSED:
        click.echo(f"Deal id {deal.deal_id} is not in Proposed state, current state: {deal.state}")
        return

    if not utils.ask_user_confirm(f"\nRejecting deal id {deal.deal_id}: {deal}"):
        click.echo("Canceled!\n")
        return

    tx_hash = PoRepMarket().reject_deal(deal.deal_id, from_private_key)
    click.echo(f"Deal id {deal.deal_id} rejected: {tx_hash}")
    return tx_hash


def accept_deal_id(deal_id: int, from_private_key: str) -> str | None:
    return accept_deal(PoRepMarket().get_deal_proposal(deal_id), from_private_key)


def reject_deal_id(deal_id: int, from_private_key: str) -> str | None:
    return reject_deal(PoRepMarket().get_deal_proposal(deal_id), from_private_key)
