import os

from cli import utils
from cli.services.contracts.contract_service import ContractService, Address


class ValidatorFactory(ContractService):
    def __init__(self, contract_address: Address | str = None):
        super().__init__(contract_address if contract_address else utils.get_env('VALIDATOR_FACTORY'),
                         os.path.dirname(os.path.realpath(__file__)) + '/abi/ValidatorFactory.json')

    # @notice Creates a new instance of an upgradeable contract.
    # @dev Uses BeaconProxy to create a new proxy instance, pointing to the Beacon for the logic contract.
    # @dev Reverts if an instance for the given dealId already exists.
    # @param dealId The dealId for which the proxy was created.
    def create(self, deal_id: int, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.create(deal_id), from_private_key)

    # @notice Gets the instance for a given deal
    # @param dealId The ID of the deal
    # @return The instance for the given deal
    def get_instance(self, deal_id: int) -> Address:
        return Address(self.contract.functions.getInstance(deal_id).call())
