import click

from cli.commands.sp._sp import sp_private_key
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal, PoRepMarket


def accept_deal(deal: PoRepMarketDealProposal) -> str:
    if deal.state != PoRepMarketDealState.PROPOSED:
        raise click.ClickException(f"Deal id {deal.deal_id} is not in PROPOSED state, current state: {deal.state}")

    click.confirm(f"Accepting deal id {deal.deal_id}: {deal}", abort=True)

    tx_hash = PoRepMarket().accept_deal(deal.deal_id, sp_private_key())
    click.echo(f"Deal id {deal.deal_id} accepted: {tx_hash}")

    return tx_hash


def reject_deal(deal: PoRepMarketDealProposal) -> str:
    if deal.state != PoRepMarketDealState.PROPOSED:
        raise click.ClickException(f"Deal id {deal.deal_id} is not in PROPOSED state, current state: {deal.state}")

    click.confirm(f"Rejecting deal id {deal.deal_id}: {deal}", abort=True)

    tx_hash = PoRepMarket().reject_deal(deal.deal_id, sp_private_key())
    click.echo(f"Deal id {deal.deal_id} rejected: {tx_hash}")

    return tx_hash
