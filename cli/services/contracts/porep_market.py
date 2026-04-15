import os
from enum import Enum

from cli import utils
from cli.services.contracts.contract_service import ContractService, Address
from cli.services.contracts.sp_registry import SPRegistrySLIThresholds


# @notice DealState enum
# @dev Represents the various states a deal can be
class PoRepMarketDealState(Enum):
    PROPOSED = 0
    ACCEPTED = 1
    COMPLETED = 2
    REJECTED = 3
    TERMINATED = 4

    @staticmethod
    def from_string(s: str):
        s = s.strip().lower()

        if s == "proposed":
            return PoRepMarketDealState.PROPOSED
        elif s == "accepted":
            return PoRepMarketDealState.ACCEPTED
        elif s == "completed":
            return PoRepMarketDealState.COMPLETED
        elif s == "rejected":
            return PoRepMarketDealState.REJECTED
        elif s == "terminated":
            return PoRepMarketDealState.TERMINATED
        else:
            raise Exception(f"Invalid deal state: {s}")

    @staticmethod
    def to_string_list():
        return [state.name for state in PoRepMarketDealState]

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self)


# @notice Commercial terms for a deal (not Oracle-measured)
@utils.json_dataclass()
class PoRepMarketDealTerms:
    deal_size_bytes: int
    price_per_sector_per_month: int  # Monthly price per 32 GiB sector in USDFC smallest units (wei-equivalent)
    duration_days: int  # Must be divisible by 30


# @param requirements The SLI thresholds for the deal
# @param terms The commercial terms for the deal
# @param manifest_location The location of the manifest for the deal
@utils.json_dataclass()
class PoRepMarketDealRequest:
    requirements: SPRegistrySLIThresholds
    terms: PoRepMarketDealTerms
    manifest_location: str


# @dev Represents a proposal for a PoRep deal, including all relevant details and terms
# @param deal_id: Unique identifier for the deal
# @param client_address: Address of the client proposing the deal
# @param provider_id: FilActor ID of the storage provider
# @param validator: Address of the validator responsible for validating the deal
# @param state: Current state of the deal (Proposed, Accepted, Completed, Rejected, Terminated)
# @param rail_id: ID of the payment rail associated with the deal
@utils.json_dataclass()
class PoRepMarketDealProposal(PoRepMarketDealRequest):
    deal_id: int
    client_address: Address
    provider_id: int
    validator_address: Address
    state: PoRepMarketDealState
    rail_id: int

    def __post_init__(self):
        self.client_address = Address(self.client_address)
        self.validator_address = Address(self.validator_address)

    @staticmethod
    def from_array(data) -> "PoRepMarketDealProposal":
        return PoRepMarketDealProposal(
            deal_id=data[0],
            client_address=data[1],
            provider_id=data[2],
            requirements=SPRegistrySLIThresholds(
                retrievability_bps=data[3][0],
                bandwidth_mbps=data[3][1],
                latency_ms=data[3][2],
                indexing_pct=data[3][3],
            ),
            terms=PoRepMarketDealTerms(
                deal_size_bytes=data[4][0],
                price_per_sector_per_month=data[4][1],
                duration_days=data[4][2],
            ),
            manifest_location=data[8],
            validator_address=data[5],
            state=PoRepMarketDealState(data[6]),
            rail_id=data[7],
        )


class PoRepMarket(ContractService):
    def __init__(self, contract_address: Address | str = None):
        super().__init__(contract_address if contract_address else utils.get_env("POREP_MARKET"),
                         os.path.dirname(os.path.realpath(__file__)) + "/abi/PoRepMarket.json")

    # @notice Proposes a deal
    def propose_deal(self, deal: PoRepMarketDealRequest, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.proposeDeal(
            (deal.requirements.retrievability_bps, deal.requirements.bandwidth_mbps, deal.requirements.latency_ms, deal.requirements.indexing_pct),
            (deal.terms.deal_size_bytes, deal.terms.price_per_sector_per_month, deal.terms.duration_days),
            deal.manifest_location
        ), from_private_key)

    # @notice Gets a deal proposal
    # @param deal_id The id of the deal proposal
    # @return PoRepMarketDealProposal The deal proposal
    def get_deal_proposal(self, deal_id: int) -> PoRepMarketDealProposal:
        deal = self.contract.functions.getDealProposal(deal_id).call()

        if not Address(deal[1]):
            raise Exception(f"Deal proposal with id {deal_id} does not exist")

        if deal_id != deal[0]:
            raise Exception(f"Invalid deal proposal returned from contract. Expected deal_id {deal_id}, got {deal[0]}")

        return PoRepMarketDealProposal.from_array(deal)

    # @notice Gets deals for a specific organization by state
    # @param organization_address The address of the organization
    # @param state The state of the deals to retrieve
    # @return deals Array of deal proposals for the organization in the specified state (from all providers associated with the organization)
    def get_deals_for_organization_by_state(self, organization_address: Address, state: PoRepMarketDealState) -> list[PoRepMarketDealProposal]:
        return [PoRepMarketDealProposal.from_array(deal) for deal in
                self.contract.functions.getDealsForOrganizationByState(organization_address, state.value).call()]

    # @notice Accepts a deal
    # @param dealId The id of the deal proposal
    def accept_deal(self, deal_id: int, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.acceptDeal(deal_id), from_private_key)

    # @notice Completes a deal
    # @param dealId The id of the deal proposal
    # @param actualSizeBytes The actual size of the deal in bytes
    def complete_deal(self, deal_id: int, actual_size_bytes: int, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.completeDeal(deal_id, actual_size_bytes), from_private_key)

    # @notice Terminate a deal
    # @dev Terminates a deal by setting the deal state to terminated
    # @param dealId The id of the deal proposal
    # @param terminator The address that terminated the deal
    # @param endEpoch The Filecoin epoch at which the deal was terminated
    def terminate_deal(self, deal_id: int, terminator: Address, end_epoch: int, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.terminateDeal(deal_id, terminator, end_epoch), from_private_key)

    # @notice Rejects a deal
    # @param dealId The id of the deal proposal
    def reject_deal(self, deal_id: int, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.rejectDeal(deal_id), from_private_key)

    # @notice Gets all completed deals
    # @return completedDeals Array of completed deal proposals
    def get_completed_deals(self) -> list[PoRepMarketDealProposal]:
        return [PoRepMarketDealProposal.from_array(deal) for deal in self.contract.functions.getCompletedDeals().call()]

    # @notice Updates the rail id for a deal proposal
    # @dev Updates the rail id for a deal proposal
    # @param dealId The id of the deal proposal
    # @param railId The id of the rail
    def update_rail_id(self, deal_id: int, rail_id: int, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.updateRailId(deal_id, rail_id), from_private_key)
