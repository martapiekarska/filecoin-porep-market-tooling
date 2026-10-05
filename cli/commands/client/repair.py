import sys
import time
from decimal import Decimal

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.client import _repair
from cli.commands.client._client import client_address, client_signer
from cli.commands.client.init_deal import init_deal
from cli.commands.client.make_allocations import make_allocations
from cli.commands.repair_utils import RetrievalSource, ensure_usdfc, find_healthy_source
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.porep_market import PoRepMarket, PoRepMarketDealState
from cli.services.contracts.porep_market_view_helper import PoRepMarketDealView, PoRepMarketViewHelper
from cli.services.self_update import SelfUpdateService

EPOCHS_PER_MONTH = 30 * 2880  # PoRep Market months are 30 days of 2880 epochs
ACCEPTANCE_POLL_SECONDS = 30
PENDING_DEAL_STATES = (PoRepMarketDealState.PROPOSED, PoRepMarketDealState.ACCEPTED)


@click.command()
@click.argument("deal_id", type=click.IntRange(min=1))
@click.option("--source-url",
              help="Override: base URL of the healthy SP's piece server / sp-proxy (e.g. https://sp.example.com:8787).  "
                   "[default: auto-detected from other providers' deals for the same dataset]")
@click.option("--price-per-tib-per-month", type=click.FloatRange(min=0, min_open=True),
              help="Maximum monthly price per 1 TiB for the new deal, in the deal's payment token.  [default: DEAL_ID's price]")
@click.option("--duration-months", type=click.IntRange(min=6),
              help="Duration of the new deal in months.  [default: DEAL_ID's duration]")
@click.option("--wait-minutes", type=click.IntRange(min=0), default=10, show_default=True,
              help="How long to wait for the matched SP to accept a newly proposed deal before stopping; re-run to resume.")
@click.option("--propose-new", is_flag=True, default=False,
              help="Propose a new repair deal even though a deal for the same dataset proposed after DEAL_ID is already "
                   "ACTIVE (e.g. it repaired a different deal of this dataset).  [default: false]")
@click.option("--allow-unverified-history", is_flag=True, default=False,
              help="Deposit even if earlier deposits to the payee can't be checked (RPC log limits); only after checking them yourself.  "
                   "[default: false]")
@click.option("--allow-repeat-deposit", is_flag=True, default=False,
              help="Deposit even though earlier deposits to the payee already cover the cost (e.g. they were for another deal with "
                   "the same SP).  [default: false]")
@click.pass_context
def repair(ctx,
           deal_id: int,
           source_url: str | None = None,
           price_per_tib_per_month: float | None = None,
           duration_months: int | None = None,
           wait_minutes: int = 10,
           propose_new: bool = False,
           allow_unverified_history: bool = False,
           allow_repeat_deposit: bool = False):
    """
    \b
    FCSS repair: re-onboard DEAL_ID's dataset with a new SP, fetching it from a healthy SP. Resumable: re-run the
    same command after any interruption and it continues from the state on-chain.

    \b
    1. Find a repair deal already proposed for DEAL_ID's dataset (same client and manifest, a different SP,
       proposed after DEAL_ID and still PROPOSED or ACCEPTED); if there is none, find a healthy SP and its exact
       retrieval quote, then propose one with DEAL_ID's terms (the market matches the SP as for any other deal),
    2. wait up to --wait-minutes for the SP to accept it,
    3. deposit the one-off retrieval cost into the FileCoinPay account of the new SP's payee (as
       `client pay-repair-retrieval`; skipped when already deposited),
    4. initialize the deal and make its DDO allocations (as `client init-deal` and `client make-allocations`).

    DEAL_ID - The deal being repaired (the SP that lost or no longer serves the data).
    """

    SelfUpdateService.check_and_prompt(manual=False)

    old_deal = PoRepMarketViewHelper().get_deal_view(deal_id)

    if old_deal.deal.client_address != client_address():
        raise click.ClickException(f"Deal ID {deal_id} client address {old_deal.deal.client_address} "
                                   f"does not match with connected client address {client_address()}.")

    _repair.ensure_repairable(old_deal)
    ensure_usdfc(old_deal.payment.payment_token, f"Deal ID {deal_id}")

    new_deal = _find_repair_deal(old_deal, propose_new)
    source = None

    if new_deal is None:
        new_deal_id, source = _propose_repair_deal(old_deal, source_url, price_per_tib_per_month, duration_months)

        if new_deal_id is None:
            click.echo("\nNo deal created.")
            return

        new_deal = PoRepMarketViewHelper().get_deal_view(new_deal_id)

    resume_command = f"`{sys.argv[0]} client repair {deal_id}" + (f" --source-url {source_url}" if source_url else "") + "`"

    if new_deal.deal.state == PoRepMarketDealState.PROPOSED:
        new_deal = _wait_for_acceptance(new_deal.deal.deal_id, wait_minutes)

    if new_deal.deal.state == PoRepMarketDealState.PROPOSED:
        click.echo(f"\nRepair deal ID {new_deal.deal.deal_id} is not accepted yet. Re-run {resume_command} once it is to continue.")
        return

    if new_deal.deal.state != PoRepMarketDealState.ACCEPTED:
        raise click.ClickException(f"Repair deal ID {new_deal.deal.deal_id} is in state {new_deal.deal.state}; re-run "
                                   f"{resume_command} to propose a new one.")

    click.echo(f"\nRepair deal ID {new_deal.deal.deal_id} accepted by provider {new_deal.deal.provider_id}.")
    _repair.pay_repair_retrieval(new_deal.deal.deal_id, deal_id, source_url, source=source,
                                 allow_unverified_history=allow_unverified_history, allow_repeat_deposit=allow_repeat_deposit,
                                 covered_is_done=True)

    ctx.invoke(init_deal, deal_id=new_deal.deal.deal_id)
    ctx.invoke(make_allocations, deal_id=new_deal.deal.deal_id)

    click.echo(f"\nRepair of deal ID {deal_id} set up as deal ID {new_deal.deal.deal_id}; the new SP now downloads the data "
               f"with `sp onboard-data {new_deal.deal.deal_id}`.")


# The CLI keeps no local state, so an earlier run's repair deal is found on-chain. Once a repair deal is ACTIVE there is nothing
# left for the client to do, so an ACTIVE deal for the dataset proposed after DEAL_ID stops the command instead of proposing again.
def _find_repair_deal(old_deal: PoRepMarketDealView, propose_new: bool) -> PoRepMarketDealView | None:
    candidates = []

    for deal in commands_utils.get_client_deals(client_address()):
        if deal.deal_id == old_deal.deal.deal_id or deal.provider_id == old_deal.deal.provider_id:
            continue

        if deal.proposed_at_epoch <= old_deal.deal.proposed_at_epoch:
            continue

        if deal.state not in PENDING_DEAL_STATES + (PoRepMarketDealState.ACTIVE,):
            continue

        view = PoRepMarketViewHelper().get_deal_view(deal.deal_id)

        if bytes(view.data.manifest_hash) == bytes(old_deal.data.manifest_hash):
            candidates.append(view)

    pending = [view for view in candidates if view.deal.state in PENDING_DEAL_STATES]
    active = [view for view in candidates if view.deal.state == PoRepMarketDealState.ACTIVE]

    if pending:
        new_deal = max(pending, key=lambda view: view.deal.deal_id)

        if len(pending) > 1:
            click.echo(f"Several pending repair deals found ({', '.join(str(view.deal.deal_id) for view in pending)}); "
                       f"continuing with the latest.")

        click.echo(f"Continuing repair deal ID {new_deal.deal.deal_id} ({new_deal.deal.state}, provider {new_deal.deal.provider_id}).")
        return new_deal

    if active and not propose_new:
        deals_str = ", ".join(f"{view.deal.deal_id} (provider {view.deal.provider_id})" for view in active)
        raise click.ClickException(f"Deal(s) {deals_str} for the same dataset were proposed after deal ID {old_deal.deal.deal_id} and are "
                                   f"ACTIVE, so the repair looks done. If they repaired another deal of this dataset, re-run with "
                                   f"--propose-new.")

    return None


def _propose_repair_deal(old_deal: PoRepMarketDealView,
                         source_url: str | None,
                         price_per_tib_per_month: float | None,
                         duration_months: int | None) -> tuple[int | None, RetrievalSource]:
    #
    manifest, _ = commands_utils.fetch_manifest(old_deal.data.manifest_location, show_manifest=False, quiet=True, retries=10)

    # show the repair cost before the proposal is confirmed
    source = find_healthy_source(old_deal.data.manifest_hash, manifest[0]["pieces"], {old_deal.deal.provider_id}, source_url)
    click.echo(f"\nOne-off repair retrieval cost quoted by {source.base_url}, paid once the matched SP accepts the deal: "
               f"{source.quote.total} USDFC for {source.quote.paid_pieces} paid piece(s)")

    # propose_deal takes whole percent and Mbps: round up, so the new deal never asks for less than the old one
    slis = old_deal.required_slis
    deal_id = commands_utils.propose_deal(client_signer(),
                                          old_deal.data.manifest_location,
                                          -(-slis.retrievability_bps // 100),
                                          -(-slis.bandwidth_bytes_per_second // utils.Mbps_to_Bps(1)),
                                          price_per_tib_per_month or _old_price_per_tib(old_deal),
                                          duration_months or _old_duration_months(old_deal),
                                          slis.latency_ms,
                                          slis.indexing_pct,
                                          old_deal.payment.payment_token,
                                          old_deal.deal.deal_type)
    return deal_id, source


# propose_deal takes a decimal price per TiB; only reuse the old price if it converts back to exactly the same per-sector price
def _old_price_per_tib(old_deal: PoRepMarketDealView) -> float:
    decimals = ERC20Contract(old_deal.payment.payment_token).decimals()
    sector_size_bytes = PoRepMarket().get_sector_size_bytes()
    price_per_sector = old_deal.payment.price_per_32_gib_per_month
    price = float(Decimal(price_per_sector * (1024 ** 4 // sector_size_bytes)).scaleb(-decimals))

    try:
        if utils.price_per_TiB_tokens_to_per_sector_wei(price, decimals, sector_size_bytes) == price_per_sector:
            return price
    except ValueError:
        pass

    raise click.UsageError(f"Deal ID {old_deal.deal.deal_id} price can't be reused exactly; set --price-per-tib-per-month.")


def _old_duration_months(old_deal: PoRepMarketDealView) -> int:
    months, remainder = divmod(old_deal.terms.duration_epochs, EPOCHS_PER_MONTH)

    if remainder or months < 6:
        raise click.UsageError(f"Deal ID {old_deal.deal.deal_id} duration of {old_deal.terms.duration_epochs} epochs is not a whole "
                               f"number of months (6 or more); set --duration-months.")

    return months


def _wait_for_acceptance(deal_id: int, wait_minutes: int) -> PoRepMarketDealView:
    deadline = time.monotonic() + wait_minutes * 60
    deal = PoRepMarketViewHelper().get_deal_view(deal_id)

    if deal.deal.state == PoRepMarketDealState.PROPOSED and wait_minutes:
        click.echo(f"\nWaiting up to {wait_minutes} minute(s) for provider {deal.deal.provider_id} to accept deal ID {deal_id}...")

    while deal.deal.state == PoRepMarketDealState.PROPOSED and time.monotonic() < deadline:
        time.sleep(ACCEPTANCE_POLL_SECONDS)
        deal = PoRepMarketViewHelper().get_deal_view(deal_id)

    return deal
