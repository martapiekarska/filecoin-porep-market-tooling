import re
from decimal import Decimal
from math import ceil

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.client._client import client_address, client_signer
from cli.commands.repair_utils import GIB_BYTES, RetrievalSource, find_healthy_source, get_manifest_repair_source
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealType
from cli.services.contracts.porep_market_view_helper import PoRepMarketDealView, PoRepMarketViewHelper
from cli.services.contracts.sp_registry import SPRegistry
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
# The healthy SP and its price are found automatically (see repair_utils.find_healthy_source).

LOGS_BLOCK_RANGE = 2000  # initial eth_getLogs block range, shrunk to the RPC provider limit if needed
MIN_LOGS_BLOCK_RANGE = 50


# Mirrors large-paid-retrievals sp-proxy pricing (README "Pricing"): each piece is billed per binary GiB, rounded up.
# The price per GiB is read from the healthy SP's quotes; sizes come from the manifest fileSize (checked against the SP).
def estimate_retrieval_cost(pieces: list[dict], price_per_gib_wei: int) -> int:
    return sum(ceil((piece.get("fileSize") or piece["pieceSize"]) / GIB_BYTES) * price_per_gib_wei for piece in pieces)


def price_to_wei(price: float | Decimal, decimals: int) -> int:
    result = Decimal(str(price)) * (10 ** decimals)

    if result != int(result):
        raise click.BadParameter(f"Price {price} has more precision than the token's {decimals} decimals")

    return int(result)


def ensure_same_dataset(deal: PoRepMarketDealView, repair_of_deal_id: int):
    repaired_deal = PoRepMarketViewHelper().get_deal_view(repair_of_deal_id)

    if bytes(repaired_deal.data.manifest_hash) != bytes(deal.data.manifest_hash):
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} manifest hash does not match repaired deal ID {repair_of_deal_id}; "
                                   f"it is not a repair of the same dataset.")


# The retrieval wallet is the SP payee recorded on-chain for the deal (set by the SP via `sp register-sp --payee-address`)
def get_retrieval_wallet(deal: PoRepMarketDealView) -> EthAddress:
    payee = deal.payment.payee

    if int(payee, 16) == 0:
        payee = SPRegistry().get_provider_view(deal.deal.provider_id).payee_address

    if int(payee, 16) == 0:
        raise click.ClickException(f"No payee address found for deal ID {deal.deal.deal_id} provider {deal.deal.provider_id}")

    # retrieval-client signs with a plain secp256k1 key, so a contract payee (e.g. multisig) cannot retrieve
    if Web3Service().w3().eth.get_code(payee):
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} payee {payee} is a contract; "
                                   f"the repair retrieval needs an externally owned payee wallet.")

    return EthAddress(payee)


# The CLI keeps no local state, so previous repair deposits are found on-chain: client -> payee deposits since the deal was proposed
def get_previous_repair_deposits(token: EthAddress, payee: EthAddress, since_block: int) -> int | None:
    filecoin_pay = FileCoinPay()
    latest_block = Web3Service().get_block_number()
    block_range = LOGS_BLOCK_RANGE
    start = since_block
    total = 0

    click.echo(f"\nChecking previous deposits to {payee} since epoch {since_block}...")

    while start <= latest_block:
        end = min(start + block_range - 1, latest_block)

        # noinspection PyBroadException
        try:
            total += filecoin_pay.get_deposited_amount(token, client_address(), payee, start, end)
            start = end + 1

        # RPC providers cap eth_getLogs block ranges differently (e.g. "block range exceeds maximum of 360"); shrink and retry
        # pylint: disable=broad-exception-caught
        except Exception as e:
            match = re.search(r"maximum of (\d+)", str(e))
            block_range = min(int(match.group(1)), block_range - 1) if match else block_range // 2

            # other errors (e.g. a provider's lookback limit for older deals) won't go away with a smaller range
            if "range" not in str(e).lower() or block_range < MIN_LOGS_BLOCK_RANGE:
                click.echo(f"WARNING: could not check previous deposits to {payee}: {e}")
                return None

    return total


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


def pay_repair_retrieval(deal_id: int,
                         repair_of_deal_id: int | None = None,
                         source_url: str | None = None,
                         price_per_gib: float | None = None,
                         token_address: str | None = None,
                         source: RetrievalSource | None = None):
    #
    Web3Service().wait_for_pending_transactions(client_address())

    deal = PoRepMarketViewHelper().get_deal_view(deal_id)

    if deal.deal.client_address != client_address():
        raise click.ClickException(f"Deal ID {deal_id} client address {deal.deal.client_address} "
                                   f"does not match with connected client address {client_address()}.")

    if deal.deal.state not in (PoRepMarketDealState.PROPOSED, PoRepMarketDealState.ACCEPTED, PoRepMarketDealState.ACTIVE):
        raise click.ClickException(f"Deal ID {deal_id} is in state {deal.deal.state}, expected PROPOSED, ACCEPTED or ACTIVE")

    if repair_of_deal_id is not None:
        ensure_same_dataset(deal, repair_of_deal_id)

    manifest, _ = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)
    pieces = manifest[0]["pieces"]

    # legacy repair: the new SP fetches from the source embedded in the deal manifest, so price that one
    embedded_source = get_manifest_repair_source(manifest)
    if embedded_source:
        if source_url and source_url.rstrip("/") != embedded_source:
            raise click.ClickException(f"Deal ID {deal_id} manifest repair source is {embedded_source}, not {source_url}")
        source_url = embedded_source

    # a source found before proposing is only reusable if the deal did not land with that same SP
    if price_per_gib is None and (source is None or source.provider_id == deal.deal.provider_id):
        source = find_repair_source(deal, pieces, repair_of_deal_id, source_url)

    if price_per_gib is None:
        assert source
        if source.is_free():
            click.echo(f"\nHealthy source {source.base_url} serves the data for free; no repair retrieval payment needed.")
            return

        price_per_gib = source.price_per_gib

    retrieval_wallet = get_retrieval_wallet(deal)

    manifest, _ = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)
    pieces = manifest[0]["pieces"]

    token = ERC20Contract(EthAddress.from_any(token_address) if token_address else deal.payment.payment_token)
    token_decimals = token.decimals()
    token_symbol = token.symbol()

    cost = estimate_retrieval_cost(pieces, price_to_wei(price_per_gib, token_decimals))
    source_str = f" from {source.base_url}" + (f" (deal {source.deal_id}, provider {source.provider_id})" if source.deal_id else "") if source else ""

    cost_str = utils.str_from_wei(cost, token_decimals)

    token_balance = token.balance_of(client_address())
    token_balance_str = utils.str_from_wei(token_balance, token_decimals)

    click.echo(f"\nRepair retrieval for deal ID {deal_id} (provider {deal.deal.provider_id}):\n"
               f"  Manifest: {deal.data.manifest_location}\n"
               f"  Pieces: {len(pieces)}, billed per GiB rounded up per piece at {price_per_gib} {token_symbol}/GiB{source_str}\n"
               f"  Estimated retrieval cost: {cost_str} {token_symbol}\n"
               f"  New SP retrieval wallet (deal payee): {retrieval_wallet}\n"
               f"  Client token balance: {token_balance_str} {token_symbol}")

    previous_deposits = get_previous_repair_deposits(token.address(), retrieval_wallet, deal.deal.proposed_at_epoch)
    if previous_deposits:
        utils.confirm(f"\nWARNING: {utils.str_from_wei(previous_deposits, token_decimals)} {token_symbol} were already deposited "
                      f"from {client_address()} to {retrieval_wallet} since deal ID {deal_id} was proposed; "
                      f"the repair retrieval may already be paid. Deposit another {cost_str} {token_symbol} anyway?", default=False, abort=True)

    if token_balance < cost:
        raise click.ClickException(f"Insufficient {token_symbol} balance {token_balance_str} for repair retrieval cost {cost_str} {token_symbol}")

    utils.confirm(f"\nDeposit {cost_str} {token_symbol} one-off from {client_address()} into the FileCoinPay account "
                  f"of deal ID {deal_id} payee {retrieval_wallet}?", abort=True)

    filecoin_pay = FileCoinPay()

    # FileCoinPay permit deposits must credit the permit signer, so a third-party deposit needs a plain ERC20 approval
    if token.allowance(client_address(), filecoin_pay.address()) < cost:
        tx_hash = token.approve(filecoin_pay.address(), cost, client_signer()).tx_hash
        click.echo(f"Approved FileCoinPay to spend {cost_str} {token_symbol}: {tx_hash}")
        Web3Service().wait_for_pending_transactions(client_address())

    tx_hash = filecoin_pay.deposit(token.address(), retrieval_wallet, cost, client_signer()).tx_hash
    click.echo(f"Deposited {cost_str} {token_symbol} for repair retrieval of deal ID {deal_id} to {retrieval_wallet}: {tx_hash}")
