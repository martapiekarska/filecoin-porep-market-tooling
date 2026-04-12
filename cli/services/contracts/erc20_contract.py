import os

from cli.services.contracts.contract_service import ContractService, Address


class ERC20Contract(ContractService):
    def __init__(self, contract_address: Address | str, contract_abi_path: str = None):
        super().__init__(contract_address,
                         contract_abi_path if contract_abi_path else os.path.dirname(os.path.realpath(__file__)) + '/abi/ERC20.json')

    def balance_of(self, account: Address) -> int:
        return self.contract.functions.balanceOf(account).call()

    def decimals(self) -> int:
        return self.contract.functions.decimals().call()

    def name(self) -> str:
        return self.contract.functions.name().call()

    def symbol(self) -> str:
        return self.contract.functions.symbol().call()
