import click

from cli.commands.client import _repair
from cli.services.self_update import SelfUpdateService


@click.command()
@click.argument("deal_id", type=click.IntRange(min=1))
@click.option("--provider-id", required=True,
              help="Provider (miner actor) ID of the new SP; must match the SP assigned to DEAL_ID.")
@click.option("--retrieval-wallet", required=True,
              help="0x wallet the new SP uses with large-paid-retrievals retrieval-client (public address only, never a key).")
@click.option("--price-per-gib", type=click.FloatRange(min=0, min_open=True), required=True,
              help="Healthy SP's sp-proxy rate (--price-usdfc-per-gb) in decimal tokens per GiB (e.g., 0.01).")
@click.option("--repair-of", type=click.IntRange(min=1),
              help="Deal ID being repaired; verifies DEAL_ID stores the same dataset (same manifest hash).")
@click.option("--token", "token_address",
              help="ERC20 token the healthy SP's sp-proxy charges in (USDFC).  [default: DEAL_ID payment token]")
def pay_repair_retrieval(deal_id: int,
                         provider_id: str,
                         retrieval_wallet: str,
                         price_per_gib: float,
                         repair_of: int | None = None,
                         token_address: str | None = None):
    """
    One-off payment of a repair retrieval for a new SP.

    \b
    Deposits the estimated large-paid-retrievals cost of DEAL_ID's data directly into the new SP's
    retrieval wallet FileCoinPay account, so the new SP can pay the healthy SP's sp-proxy without
    fronting the cost and without any client keys. This is separate from and in addition to the
    regular deal payment (`client init-deal`). The same step runs as part of `client propose-deal --repair`.

    DEAL_ID - The new (repair) deal ID.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    _repair.pay_repair_retrieval(deal_id, retrieval_wallet, price_per_gib, provider_id, repair_of, token_address)
