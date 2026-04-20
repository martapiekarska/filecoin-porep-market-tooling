import os
from collections import namedtuple

from eth_account.types import PrivateKeyType

from cli import utils
from cli.services.contracts.contract_service import ContractService, Address


class ClientContract(ContractService):
    TransferParams = namedtuple("TransferParams", ["to", "amount", "operator_data"])

    def __init__(self, contract_address: Address | None = None):
        super().__init__(contract_address if contract_address else utils.get_env_required("CLIENT_CONTRACT", required_type=Address),
                         os.path.dirname(os.path.realpath(__file__)) + "/abi/Client.json")

    def transfer(self, transfer_params: tuple, deal_id: int, deal_completed: bool, from_private_key: PrivateKeyType) -> str:
        return self.sign_and_send_tx(self.contract.functions.transfer(transfer_params, deal_id, deal_completed), from_private_key)
