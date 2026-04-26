import os

from eth_account.types import PrivateKeyType

from cli import utils
from cli.services.contracts.contract_service import ContractService, Address


@utils.json_dataclass()
class TransferParams:
    to: Address
    amount: int
    operator_data: str

    def __post_init__(self):
        self.to = Address(self.to)


class ClientContract(ContractService):
    def __init__(self, contract_address: Address | None = None):
        super().__init__(contract_address if contract_address else utils.get_env_required("CLIENT_CONTRACT", required_type=Address),
                         os.path.dirname(os.path.realpath(__file__)) + "/abi/Client.json")

    # @notice This function transfers DataCap tokens from the client to the storage provider
    # @dev This function can only be called by the client
    # @param params The parameters for the transfer
    # @dev Reverts with InsufficientAllowance if caller doesn't have sufficient allowance
    # @dev Reverts with InvalidAmount when parsing amount from BigInt to uint256 failed
    # @dev Reverts with UnfairDistribution when trying to give too much to single SP
    def transfer(self, transfer_params: TransferParams, deal_id: int, deal_completed: bool, from_private_key: PrivateKeyType) -> str:
        return self.sign_and_send_tx(self.contract.functions.transfer(transfer_params, deal_id, deal_completed), from_private_key)

    # @notice custom getter to retrieve allocation ids per client and provider
    # @param dealId the id of the deal
    # @return allocationIds the allocation ids for the client and provider
    def get_client_allocation_ids_per_deal(self, deal_id: int) -> list[int]:
        return self.contract.functions.getClientAllocationIdsPerDeal(deal_id).call()
