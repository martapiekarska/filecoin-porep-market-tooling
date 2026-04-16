#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Non-interactive cron-friendly helper for Storage Providers (SPs).

What it does:
- Fetches all PROPOSED deals for your organization (PoRepMarket.getDealsForOrganizationByState)
- Optionally sends acceptDeal() for each proposed deal (no interactive confirmations)
- Prints a readiness report for all deals (proposed/accepted/completed) so you can see whether
  the client has created the validator, created the FilecoinPay rail, and started allocations.

Expected environment variables (see .env.example):
- RPC_URL
- POREP_MARKET
- SP_REGISTRY
- CLIENT_CONTRACT
- SP_PRIVATE_KEY

Optional environment variables:
- SP_ORGANIZATION_ADDRESS: if omitted, derived from SP_PRIVATE_KEY
- SP_PROVIDER_ID: restrict actions/report to this provider id (f0... or numeric). If omitted, includes all providers under org.
- AUTO_ACCEPT: default "false". If "true", will broadcast acceptDeal txs.
- DRY_RUN: default "true" (matches CLI default). If true, will simulate tx hash.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Any

import dotenv
from web3 import Web3

from cli import utils
from cli._cli import DRY_RUN as _CLI_DRY_RUN_FLAG  # imported to satisfy type checkers; value not used
from cli.services.contracts.contract_service import Address, ContractService
from cli.services.contracts.porep_market import PoRepMarket, PoRepMarketDealProposal, PoRepMarketDealState
from cli.services.contracts.sp_registry import SPRegistry


@dataclass
class DealReadiness:
    deal_id: int
    provider_id: int
    state: str
    client: str
    manifest_location: str
    validator_set: bool
    rail_created: bool
    allocation_ids_count: int | None
    status: str


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    raise ValueError(f"Invalid boolean for {name}: {raw}")


def _derive_address_from_private_key(private_key: str) -> Address:
    w3 = Web3()
    acct = w3.eth.account.from_key(private_key)
    return Address(acct.address)


def _noninteractive_sign_and_send(contract: ContractService, fn, from_private_key: str, dry_run: bool) -> str:
    """
    Copy of ContractService.sign_and_send_tx behavior but WITHOUT interactive confirmation.
    """
    from_address = contract.w3.eth.account.from_key(from_private_key).address
    nonce = ContractService.get_address_nonce(from_address, contract.w3)
    tx_params = fn.build_transaction({"from": from_address, "nonce": nonce})
    return contract._sign_and_send_tx(fn, tx_params, from_private_key, dry_run)  # noqa: SLF001 (intentional)


def _load_client_contract() -> ContractService:
    # Reuse ContractService directly with Client ABI (tooling keeps ABIs vendored).
    abi_path = os.path.join(os.path.dirname(__file__), "..", "cli", "services", "contracts", "abi", "Client.json")
    return ContractService(utils.get_env("CLIENT_CONTRACT"), abi_path)


def _get_org_address(sp_private_key: str) -> Address:
    org = os.getenv("SP_ORGANIZATION_ADDRESS")
    if org:
        return Address(org)
    return _derive_address_from_private_key(sp_private_key)


def _provider_filter_ids(org: Address) -> tuple[int | None, set[int]]:
    """
    Returns (explicit_provider_id, provider_ids_under_org).
    If SP_PROVIDER_ID is set, explicit_provider_id is used for filtering and returned set contains it (if registered under org).
    Otherwise explicit_provider_id is None and the set contains all providers under org.
    """
    sp_registry = SPRegistry()
    provider_ids_under_org = set(int(x) for x in sp_registry.get_providers_by_organization(org))

    raw = os.getenv("SP_PROVIDER_ID")
    if not raw:
        return None, provider_ids_under_org

    explicit = utils.f0_str_id_to_int(raw)
    if explicit is None:
        raise ValueError("SP_PROVIDER_ID is set but could not be parsed")

    return explicit, {explicit}


def _fetch_deals_for_org(porep: PoRepMarket, org: Address) -> list[PoRepMarketDealProposal]:
    deals: list[PoRepMarketDealProposal] = []
    for state in (
        PoRepMarketDealState.PROPOSED,
        PoRepMarketDealState.ACCEPTED,
        PoRepMarketDealState.COMPLETED,
    ):
        deals.extend(porep.get_deals_for_organization_by_state(org, state))
    # Filter out any Nones defensively
    return [d for d in deals if d is not None]


def _readiness_for_deal(deal: PoRepMarketDealProposal, client_contract: ContractService) -> DealReadiness:
    validator_set = bool(deal.validator_address) and deal.validator_address != Address.ZERO_ADDRESS
    rail_created = deal.rail_id is not None and int(deal.rail_id) != 0

    allocation_ids_count: int | None = None
    status: str

    if deal.state == PoRepMarketDealState.PROPOSED:
        status = "proposed_waiting_sp_accept"
    elif deal.state == PoRepMarketDealState.ACCEPTED:
        if not validator_set:
            status = "accepted_waiting_client_validator"
        elif not rail_created:
            status = "accepted_waiting_client_rail"
        else:
            # This call is cheap and helps determine whether client started verified allocations/claim extensions.
            try:
                ids = client_contract.contract.functions.getClientAllocationIdsPerDeal(int(deal.deal_id)).call()
                allocation_ids_count = len(ids)
            except Exception:
                allocation_ids_count = None

            if allocation_ids_count and allocation_ids_count > 0:
                status = "accepted_rail_ready_client_allocations_started"
            else:
                status = "accepted_rail_ready_waiting_client_allocations"
    elif deal.state == PoRepMarketDealState.COMPLETED:
        # Deal has been marked completed by the Client contract; verified size is committed to the registry.
        try:
            ids = client_contract.contract.functions.getClientAllocationIdsPerDeal(int(deal.deal_id)).call()
            allocation_ids_count = len(ids)
        except Exception:
            allocation_ids_count = None
        status = "completed_ready_to_seal"
    else:
        status = f"state_{deal.state}"

    return DealReadiness(
        deal_id=int(deal.deal_id),
        provider_id=int(deal.provider_id),
        state=str(deal.state),
        client=str(deal.client_address),
        manifest_location=str(deal.manifest_location),
        validator_set=validator_set,
        rail_created=rail_created,
        allocation_ids_count=allocation_ids_count,
        status=status,
    )


def main() -> int:
    dotenv.load_dotenv()

    # Inputs
    sp_private_key = utils.get_env("SP_PRIVATE_KEY")
    org = _get_org_address(sp_private_key)
    auto_accept = _env_bool("AUTO_ACCEPT", default=False)
    dry_run = _env_bool("DRY_RUN", default=True)

    explicit_provider_id, provider_ids = _provider_filter_ids(org)

    porep = PoRepMarket()
    client_contract = _load_client_contract()

    deals = _fetch_deals_for_org(porep, org)

    # Only keep deals for providers under this org (and optional explicit SP_PROVIDER_ID).
    deals = [d for d in deals if int(d.provider_id) in provider_ids]

    proposed = [d for d in deals if d.state == PoRepMarketDealState.PROPOSED]

    accepted_txs: list[dict[str, Any]] = []
    errors: list[str] = []

    if auto_accept and proposed:
        for d in proposed:
            try:
                fn = porep.contract.functions.acceptDeal(int(d.deal_id))
                tx_hash = _noninteractive_sign_and_send(porep, fn, sp_private_key, dry_run=dry_run)
                accepted_txs.append({"deal_id": int(d.deal_id), "tx_hash": tx_hash})
            except Exception as e:
                errors.append(f"accept_deal_failed deal_id={d.deal_id}: {type(e).__name__}: {e}")

    readiness = [_readiness_for_deal(d, client_contract) for d in deals]

    output = {
        "organization_address": str(org),
        "provider_id_filter": explicit_provider_id,
        "auto_accept": auto_accept,
        "dry_run": dry_run,
        "deals_total": len(deals),
        "deals_proposed": len([d for d in deals if d.state == PoRepMarketDealState.PROPOSED]),
        "deals_accepted": len([d for d in deals if d.state == PoRepMarketDealState.ACCEPTED]),
        "deals_completed": len([d for d in deals if d.state == PoRepMarketDealState.COMPLETED]),
        "accept_transactions": accepted_txs,
        "readiness": [asdict(r) for r in readiness],
        "errors": errors,
    }

    print(json.dumps(output, indent=2))

    # Exit non-zero if we attempted accepts and had failures.
    if errors and auto_accept:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

