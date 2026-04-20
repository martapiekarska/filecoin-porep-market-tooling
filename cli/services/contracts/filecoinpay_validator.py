import os

from eth_account.types import PrivateKeyType

from cli.services.contracts.contract_service import ContractService, Address


class FileCoinPayValidator(ContractService):
    def __init__(self, contract_address: Address):
        super().__init__(contract_address,
                         os.path.dirname(os.path.realpath(__file__)) + '/abi/Validator.json')

    # @notice Creates a payment rail with the specified parameters and set initial lockup period
    # @dev Only callable by the client
    # @dev Sets railID in contract state and updates the PoRepMarket with the created rail ID
    # @param token The ERC20 token to use for the payment rail
    def create_rail(self, token_address: Address, from_private_key: PrivateKeyType) -> str:
        return self.sign_and_send_tx(self.contract.functions.createRail(token_address), from_private_key)
