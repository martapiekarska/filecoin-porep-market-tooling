import os

from cli.services.contracts.contract_service import Address
from cli.services.contracts.erc20_contract import ERC20Contract
from cli import utils


class USDCToken(ERC20Contract):
    def __init__(self, contract_address: Address | str = None):
        super().__init__(contract_address if contract_address else utils.get_env('USDC_TOKEN'),
                         os.path.dirname(os.path.realpath(__file__)) + '/abi/USDC.json')

    def nonces(self, account: Address) -> int:
        return self.contract.functions.nonces(account).call()
