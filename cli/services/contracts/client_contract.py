import os
from enum import Enum

from cli import utils
from cli.services.contracts.contract_service import ContractService, Address
from collections import namedtuple

class DataCapTypes:
    TransferParams = namedtuple("TransferParams", ["to", "amount", "operator_data"])
    

class Client(ContractService):
    def __init__(self, contract_address: Address | str = None):
        super().__init__(contract_address if contract_address else utils.get_env("CLIENT_CONTRACT"),
                         os.path.dirname(os.path.realpath(__file__)) + "/abi/Client.json")

    def transfer(self, transfer_params: list[str], deal_id: int, deal_completed: bool, from_private_key: str) -> str:
        return self.sign_and_send_tx(self.contract.functions.transfer(transfer_params, deal_id, deal_completed), from_private_key)