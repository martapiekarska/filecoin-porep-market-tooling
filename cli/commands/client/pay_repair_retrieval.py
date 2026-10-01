import click

from cli.commands.client import _repair
from cli.services.self_update import SelfUpdateService


@click.command()
@click.argument("deal_id", type=click.IntRange(min=1))
@click.option("--provider-id",
              help="Expected provider (miner actor) ID of the new SP; refuse to pay if DEAL_ID is assigned to another SP.")
@click.option("--price-per-gib", type=click.FloatRange(min=0, min_open=True), required=True,
              help="Healthy SP's sp-proxy rate (--price-usdfc-per-gb) in decimal tokens per GiB (e.g., 0.01).")
@click.option("--repair-of", type=click.IntRange(min=1),
              help="Deal ID being repaired; verifies DEAL_ID stores the same dataset (same manifest hash).")
@click.option("--token", "token_address",
              help="ERC20 token the healthy SP's sp-proxy charges in (USDFC).  [default: DEAL_ID payment token]")
def pay_repair_retrieval(deal_id: int,
                         price_per_gib: float,
                         provider_id: str | None = None,
                         repair_of: int | None = None,
                         token_address: str | None = None):
    """
    One-off payment of a repair retrieval for a new SP.

    \b
    Deposits the estimated large-paid-retrievals cost of DEAL_ID's data directly into the FileCoinPay
    account of DEAL_ID's SP payee (the SP wallet recorded on-chain for the deal), so the new SP can pay
    the healthy SP's sp-proxy with it, without fronting the cost and without any client keys or
    off-chain coordination. This is separate from and in addition to the regular deal payment
    (`client init-deal`). The same step runs as part of `client propose-deal --repair`.

    DEAL_ID - The new (repair) deal ID.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    _repair.pay_repair_retrieval(deal_id, price_per_gib, repair_of, provider_id, token_address)
