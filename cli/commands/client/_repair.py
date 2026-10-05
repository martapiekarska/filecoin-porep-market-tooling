from decimal import ROUND_CEILING, Decimal, localcontext

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.client._client import client_address, client_signer
from cli.commands.repair_utils import (
    RetrievalSource,
    find_healthy_source,
    get_manifest_repair_source,
    repair_payment_token,
    resolve_repair_payee,
)
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealType
from cli.services.contracts.porep_market_view_helper import PoRepMarketDealView, PoRepMarketViewHelper
from cli.services.web3_service import EthAddress, Web3Service

# FCSS repair flow: a new SP re-onboards a dataset by retrieving it from the surviving ("healthy") SP's
# large-paid-retrievals sp-proxy (https://github.com/fidlabs/large-paid-retrievals).
#
# The sp-proxy only accepts a Filecoin Pay rail payment whose payer (rail `from`) is the same wallet that signs the
# MPP retrieval credential, i.e. the wallet that downloads. So the client cannot pay the healthy SP directly on
# behalf of the new SP. Instead the client makes a one-off FileCoinPay `deposit(token, to=<new deal's SP payee>)`:
# the payee is the SP wallet already recorded on-chain for the deal, and the LPR retrieval-client (run by the new SP
# with the payee key) spends available FileCoinPay funds before touching the wallet. So the new SP never fronts the
# retrieval cost, the client's exposure is capped at the deposited amount, and no keys or addresses are exchanged.
# The healthy SP and its price are found automatically (see repair_utils.find_healthy_source), or come from a legacy
# repair manifest's embedded source. The deposit is only made once the SP has accepted the deal, and fails closed when
# earlier deposits can't be checked (see _check_previous_deposits).

LOGS_BLOCK_RANGE = 2000  # initial eth_getLogs block range (LOGS_BLOCK_RANGE env overrides); halved on each RPC error
MIN_LOGS_BLOCK_RANGE = 50  # below this, give up and fail closed


# quotes are decimal USDFC strings; deposits are base units (rounded up, so a deposit never falls short of the quote)
def tokens_to_base_units(amount: Decimal, decimals: int) -> int:
    with localcontext() as ctx:
        ctx.prec = 100
        return int(amount.scaleb(decimals).to_integral_value(rounding=ROUND_CEILING))


def ensure_same_dataset(deal: PoRepMarketDealView, repair_of_deal_id: int):
    repaired_deal = PoRepMarketViewHelper().get_deal_view(repair_of_deal_id)

    if bytes(repaired_deal.data.manifest_hash) != bytes(deal.data.manifest_hash):
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} manifest hash does not match repaired deal ID {repair_of_deal_id}; "
                                   f"it is not a repair of the same dataset.")


class DepositHistoryUnavailable(Exception):
    pass


# The CLI keeps no local state, so previous repair deposits are found on-chain: client -> payee deposits since the deal was proposed.
# RPC providers limit eth_getLogs block ranges differently, so the range starts at LOGS_BLOCK_RANGE (env) and is halved on
# any error; errors a smaller range can't fix (e.g. a lookback limit for older deals) end in DepositHistoryUnavailable.
def get_previous_repair_deposits(token: EthAddress, payee: EthAddress, since_block: int) -> int:
    filecoin_pay = FileCoinPay()
    latest_block = Web3Service().get_block_number()
    block_range = utils.get_env_required("LOGS_BLOCK_RANGE", default=LOGS_BLOCK_RANGE, required_type=int)
    start = since_block
    total = 0

    click.echo(f"\nChecking previous deposits to {payee} since epoch {since_block}...")

    while start <= latest_block:
        end = min(start + block_range - 1, latest_block)

        # noinspection PyBroadException
        try:
            total += filecoin_pay.get_deposited_amount(token, client_address(), payee, start, end)
            start = end + 1

        # pylint: disable=broad-exception-caught
        except Exception as e:
            block_range //= 2

            if block_range < MIN_LOGS_BLOCK_RANGE:
                raise DepositHistoryUnavailable(f"RPC could not serve deposit logs for epochs {start}-{end}: {e}") from e

    return total


# Fails closed: a repeat deposit can only be recovered by the SP returning it. Returns the amount to deposit.
def _check_previous_deposits(token: EthAddress, payee: EthAddress, since_block: int, cost: int, token_decimals: int, token_symbol: str,
                             allow_unverified_history: bool, allow_repeat_deposit: bool) -> int:
    #
    def amount_str(amount: int) -> str:
        return f"{utils.str_from_wei(amount, token_decimals)} {token_symbol}"

    try:
        previous = get_previous_repair_deposits(token, payee, since_block)

    except DepositHistoryUnavailable as e:
        if not allow_unverified_history:
            raise click.ClickException(f"Could not check earlier deposits to {payee}, so a double payment can't be ruled out: {e}\n"
                                       f"Use an RPC_URL that serves logs back to epoch {since_block}, or check the payee's deposits yourself "
                                       f"and re-run with --allow-unverified-history.") from e

        utils.confirm(f"\nWARNING: earlier deposits to {payee} could not be checked ({e}); you confirmed they were checked "
                      f"another way. Deposit {amount_str(cost)}?", default=False, abort=True)
        return cost

    if previous >= cost:
        if not allow_repeat_deposit:
            raise click.ClickException(f"{amount_str(previous)} were already deposited from {client_address()} to {payee} since the deal "
                                       f"was proposed, covering the {amount_str(cost)} repair cost; not depositing again. If those deposits "
                                       f"were for another deal with the same SP, re-run with --allow-repeat-deposit.")

        utils.confirm(f"\nWARNING: {amount_str(previous)} already deposited to {payee} since the deal was proposed. "
                      f"Deposit another {amount_str(cost)}?", default=False, abort=True)
        return cost

    if previous > 0:
        shortfall = cost - previous
        click.echo(f"\n{amount_str(previous)} already deposited to {payee} since the deal was proposed; "
                   f"the remaining repair cost is {amount_str(shortfall)}.")
        return shortfall

    return cost


def find_repair_source(deal: PoRepMarketDealView,
                       pieces: list[dict],
                       repair_of_deal_id: int | None = None,
                       source_url: str | None = None) -> RetrievalSource:
    #
    exclude = {deal.deal.provider_id}

    if repair_of_deal_id is not None:
        exclude.add(PoRepMarketViewHelper().get_deal_view(repair_of_deal_id).deal.provider_id)

    return find_healthy_source(deal.data.manifest_hash, pieces, exclude, source_url)


def ensure_repairable(deal: PoRepMarketDealView):
    if deal.deal.deal_type != PoRepMarketDealType.PUBLIC:
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} is {deal.deal.deal_type}; large-paid-retrievals only serves private deals "
                                   f"to their owner, so the new SP could not retrieve the data. Only PUBLIC deals can be repaired.")


# the deposit goes straight to the SP's payee and can't be clawed back, so it waits until the SP has accepted the deal
PAYABLE_DEAL_STATES = (PoRepMarketDealState.ACCEPTED, PoRepMarketDealState.ACTIVE)


def pay_repair_retrieval(deal_id: int,
                         repair_of_deal_id: int | None = None,
                         source_url: str | None = None,
                         source: RetrievalSource | None = None,
                         allow_unverified_history: bool = False,
                         allow_repeat_deposit: bool = False):
    #
    Web3Service().wait_for_pending_transactions(client_address())

    deal = PoRepMarketViewHelper().get_deal_view(deal_id)

    if deal.deal.client_address != client_address():
        raise click.ClickException(f"Deal ID {deal_id} client address {deal.deal.client_address} "
                                   f"does not match with connected client address {client_address()}.")

    if deal.deal.state == PoRepMarketDealState.PROPOSED:
        raise click.ClickException(f"Deal ID {deal_id} is still PROPOSED. The repair deposit goes straight to the SP's payee and can only "
                                   f"be returned by the SP, so it is made once the SP has accepted the deal; run this again then.")

    if deal.deal.state not in PAYABLE_DEAL_STATES:
        raise click.ClickException(f"Deal ID {deal_id} is in state {deal.deal.state}, expected ACCEPTED or ACTIVE")

    if repair_of_deal_id is not None:
        ensure_same_dataset(deal, repair_of_deal_id)

    token = ERC20Contract(repair_payment_token(deal))  # refuses non-USDFC deals before anything is probed or paid

    manifest, _ = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)
    pieces = manifest[0]["pieces"]

    # legacy repair: the new SP fetches from the source embedded in the deal manifest, so price that one
    embedded_source = get_manifest_repair_source(manifest)
    if embedded_source:
        if source_url and source_url.rstrip("/") != embedded_source:
            raise click.ClickException(f"Deal ID {deal_id} manifest repair source is {embedded_source}, not {source_url}")
        source_url = embedded_source

    # a source found before proposing is only reusable if the deal did not land with that same SP
    if source is None or source.provider_id == deal.deal.provider_id:
        source = find_repair_source(deal, pieces, repair_of_deal_id, source_url)

    if source.is_free():
        click.echo(f"\nHealthy source {source.base_url} serves the data for free; no repair retrieval payment needed.")
        return

    payee = resolve_repair_payee(deal)

    token_decimals = token.decimals()
    token_symbol = token.symbol()

    cost = tokens_to_base_units(source.quote.total, token_decimals)
    source_str = f"{source.base_url}" + (f" (deal {source.deal_id}, provider {source.provider_id})" if source.deal_id else "")

    cost_str = utils.str_from_wei(cost, token_decimals)

    token_balance = token.balance_of(client_address())
    token_balance_str = utils.str_from_wei(token_balance, token_decimals)

    click.echo(f"\nRepair retrieval for deal ID {deal_id} (provider {deal.deal.provider_id}):\n"
               f"  Manifest: {deal.data.manifest_location}\n"
               f"  Source: {source_str}\n"
               f"  Pieces: {len(pieces)} ({source.quote.paid_pieces} paid, {source.quote.free_pieces} free)\n"
               f"  Retrieval cost quoted by the source: {cost_str} {token_symbol}\n"
               f"  Paid into the FileCoinPay account of the new SP's payee: {payee}\n"
               f"  Client token balance: {token_balance_str} {token_symbol}")

    deposit = _check_previous_deposits(token.address(), payee, deal.deal.proposed_at_epoch, cost, token_decimals, token_symbol,
                                       allow_unverified_history, allow_repeat_deposit)
    deposit_str = utils.str_from_wei(deposit, token_decimals)

    if token_balance < deposit:
        raise click.ClickException(f"Insufficient {token_symbol} balance {token_balance_str} for repair retrieval deposit {deposit_str} {token_symbol}")

    utils.confirm(f"\nDeposit {deposit_str} {token_symbol} one-off from {client_address()} into the FileCoinPay account "
                  f"of deal ID {deal_id} payee {payee}?\n"
                  f"This deposit is NOT refundable through this CLI or FileCoinPay: only the SP can return it.", abort=True)

    filecoin_pay = FileCoinPay()

    # FileCoinPay permit deposits must credit the permit signer, so a third-party deposit needs a plain ERC20 approval
    if token.allowance(client_address(), filecoin_pay.address()) < deposit:
        tx_hash = token.approve(filecoin_pay.address(), deposit, client_signer()).tx_hash
        click.echo(f"Approved FileCoinPay to spend {deposit_str} {token_symbol}: {tx_hash}")
        Web3Service().wait_for_pending_transactions(client_address())

    tx_hash = filecoin_pay.deposit(token.address(), payee, deposit, client_signer()).tx_hash
    click.echo(f"Deposited {deposit_str} {token_symbol} for repair retrieval of deal ID {deal_id} to {payee}: {tx_hash}")
