from decimal import Decimal
from math import ceil

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.client._client import client_address, client_signer
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.porep_market import PoRepMarketDealState
from cli.services.contracts.porep_market_view_helper import PoRepMarketDealView, PoRepMarketViewHelper
from cli.services.web3_service import ActorId, EthAddress, Web3Service

# FCSS repair flow: a new SP re-onboards a dataset by retrieving it from the surviving ("healthy") SP's
# large-paid-retrievals sp-proxy (https://github.com/fidlabs/large-paid-retrievals).
#
# The sp-proxy only accepts a Filecoin Pay rail payment whose payer (rail `from`) is the same wallet that signs the
# MPP retrieval credential, i.e. the wallet that downloads. So the client cannot pay the healthy SP directly on
# behalf of the new SP. Instead the client makes a one-off FileCoinPay `deposit(token, to=<new SP retrieval wallet>)`:
# the LPR retrieval-client spends available FileCoinPay funds before touching the wallet, so the new SP never fronts
# the retrieval cost, and the client's exposure is capped at the deposited amount with no key sharing.

GIB_BYTES = 2 ** 30


# Mirrors large-paid-retrievals sp-proxy pricing (README "Pricing"): each piece is billed per binary GiB, rounded up.
# This is an upfront estimate from the manifest fileSize; the sp-proxy quotes from upstream HEAD Content-Length.
def estimate_retrieval_cost(pieces: list[dict], price_per_gib_wei: int) -> int:
    return sum(ceil((piece.get("fileSize") or piece["pieceSize"]) / GIB_BYTES) * price_per_gib_wei for piece in pieces)


def price_to_wei(price: float, decimals: int) -> int:
    result = Decimal(str(price)) * (10 ** decimals)

    if result != int(result):
        raise click.BadParameter(f"Price {price} has more precision than the token's {decimals} decimals")

    return int(result)


def ensure_same_dataset(deal: PoRepMarketDealView, repair_of_deal_id: int):
    repaired_deal = PoRepMarketViewHelper().get_deal_view(repair_of_deal_id)

    if bytes(repaired_deal.data.manifest_hash) != bytes(deal.data.manifest_hash):
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} manifest hash does not match repaired deal ID {repair_of_deal_id}; "
                                   f"it is not a repair of the same dataset.")


def pay_repair_retrieval(deal_id: int,
                         retrieval_wallet: str,
                         price_per_gib: float,
                         provider_id: str,
                         repair_of_deal_id: int | None = None,
                         token_address: str | None = None):
    #
    Web3Service().wait_for_pending_transactions(client_address())

    deal = PoRepMarketViewHelper().get_deal_view(deal_id)
    _retrieval_wallet = EthAddress.from_any(retrieval_wallet)

    if deal.deal.client_address != client_address():
        raise click.ClickException(f"Deal ID {deal_id} client address {deal.deal.client_address} "
                                   f"does not match with connected client address {client_address()}.")

    if deal.deal.state not in (PoRepMarketDealState.PROPOSED, PoRepMarketDealState.ACCEPTED, PoRepMarketDealState.ACTIVE):
        raise click.ClickException(f"Deal ID {deal_id} is in state {deal.deal.state}, expected PROPOSED, ACCEPTED or ACTIVE")

    # the retrieval wallet is only known off-chain, so pin it to the SP that actually got the deal
    if deal.deal.provider_id != ActorId(provider_id):
        raise click.ClickException(f"Deal ID {deal_id} is assigned to provider {deal.deal.provider_id}, not {provider_id}; "
                                   f"refusing to fund retrieval wallet {_retrieval_wallet} for a different SP.")

    if repair_of_deal_id is not None:
        ensure_same_dataset(deal, repair_of_deal_id)

    manifest, _ = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)
    pieces = manifest[0]["pieces"]

    token = ERC20Contract(EthAddress.from_any(token_address) if token_address else deal.payment.payment_token)
    token_decimals = token.decimals()
    token_symbol = token.symbol()

    cost = estimate_retrieval_cost(pieces, price_to_wei(price_per_gib, token_decimals))
    cost_str = utils.str_from_wei(cost, token_decimals)

    filecoin_pay = FileCoinPay()
    wallet_account = filecoin_pay.get_account(token.address(), _retrieval_wallet)
    wallet_available = wallet_account.funds - wallet_account.lockup_current
    wallet_available_str = utils.str_from_wei(wallet_available, token_decimals)

    token_balance = token.balance_of(client_address())
    token_balance_str = utils.str_from_wei(token_balance, token_decimals)

    click.echo(f"\nRepair retrieval for deal ID {deal_id} (provider {deal.deal.provider_id}):\n"
               f"  Manifest: {deal.data.manifest_location}\n"
               f"  Pieces: {len(pieces)}, billed per GiB rounded up per piece at {price_per_gib} {token_symbol}/GiB\n"
               f"  Estimated retrieval cost: {cost_str} {token_symbol}\n"
               f"  New SP retrieval wallet: {_retrieval_wallet}\n"
               f"  Retrieval wallet FileCoinPay available funds: {wallet_available_str} {token_symbol}\n"
               f"  Client token balance: {token_balance_str} {token_symbol}")

    # the CLI keeps no local state, so this is the guard against paying twice when re-running
    if wallet_available >= cost:
        utils.confirm(f"\nWARNING: retrieval wallet {_retrieval_wallet} already has enough FileCoinPay funds to cover the retrieval; "
                      f"it may already have been paid. Deposit another {cost_str} {token_symbol} anyway?", default=False, abort=True)

    if token_balance < cost:
        raise click.ClickException(f"Insufficient {token_symbol} balance {token_balance_str} for repair retrieval cost {cost_str} {token_symbol}")

    utils.confirm(f"\nDeposit {cost_str} {token_symbol} one-off from {client_address()} into the FileCoinPay account "
                  f"of new SP retrieval wallet {_retrieval_wallet}?", abort=True)

    # FileCoinPay permit deposits must credit the permit signer, so a third-party deposit needs a plain ERC20 approval
    if token.allowance(client_address(), filecoin_pay.address()) < cost:
        tx_hash = token.approve(filecoin_pay.address(), cost, client_signer()).tx_hash
        click.echo(f"Approved FileCoinPay to spend {cost_str} {token_symbol}: {tx_hash}")
        Web3Service().wait_for_pending_transactions(client_address())

    tx_hash = filecoin_pay.deposit(token.address(), _retrieval_wallet, cost, client_signer()).tx_hash
    click.echo(f"Deposited {cost_str} {token_symbol} for repair retrieval of deal ID {deal_id} to {_retrieval_wallet}: {tx_hash}")
