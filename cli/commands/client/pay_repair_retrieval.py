import click

from cli.commands.client import _repair
from cli.services.self_update import SelfUpdateService


@click.command()
@click.argument("deal_id", type=click.IntRange(min=1))
@click.option("--repair-of", type=click.IntRange(min=1),
              help="Deal ID being repaired; verifies DEAL_ID stores the same dataset (same manifest hash) "
                   "and excludes its SP as a retrieval source.")
@click.option("--source-url",
              help="Override: base URL of the healthy SP's piece server / sp-proxy (e.g. https://sp.example.com:8787).  "
                   "[default: auto-detected from other providers' deals for the same dataset]")
@click.option("--price-per-gib", type=click.FloatRange(min=0, min_open=True),
              help="Override: retrieval price in decimal tokens per GiB.  [default: quoted by the healthy SP]")
@click.option("--token", "token_address",
              help="ERC20 token the healthy SP's sp-proxy charges in (USDFC).  [default: DEAL_ID payment token]")
def pay_repair_retrieval(deal_id: int,
                         repair_of: int | None = None,
                         source_url: str | None = None,
                         price_per_gib: float | None = None,
                         token_address: str | None = None):
    """
    One-off payment of a repair retrieval for a new SP.

    \b
    1. Find a healthy SP still serving DEAL_ID's dataset: another provider's ACTIVE, PUBLIC deal with the same
       manifest hash and claims on-chain, whose advertised piece endpoint serves the data,
    2. read its retrieval price from its large-paid-retrievals sp-proxy quotes (nothing to pay if it serves for free),
    3. deposit the retrieval cost into the FileCoinPay account of DEAL_ID's SP payee, so the new SP can pay the
       healthy SP without fronting the cost and without any client keys or off-chain coordination.

    This is separate from and in addition to the regular deal payment (`client init-deal`).
    The same step runs as part of `client propose-deal --repair`.

    DEAL_ID - The new (repair) deal ID.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    _repair.pay_repair_retrieval(deal_id, repair_of, source_url, price_per_gib, token_address)
