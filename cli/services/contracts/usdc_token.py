import os

from cli import utils
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.web3_service import Address


class USDCToken(ERC20Contract):
    def __init__(self, contract_address: Address | None = None):
        super().__init__(contract_address or utils.get_env_required("USDC_TOKEN", required_type=Address),
                         os.path.dirname(os.path.realpath(__file__)) + "/abi/USDC.json")

    def nonces(self, account: Address) -> int:
        return self.contract.functions.nonces(account).call()
