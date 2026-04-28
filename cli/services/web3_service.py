from hexbytes import HexBytes
from eth_account.datastructures import SignedTransaction
import time
import click
from web3.contract import Contract
from web3.exceptions import Web3RPCError
from eth_account.types import PrivateKeyType
from web3 import Web3

from cli import utils


class Web3Service:
    _instance: "Web3Service | None" = None

    def __new__(cls) -> "Web3Service":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_w3'):
            return
        self._w3 = Web3(Web3.HTTPProvider(utils.get_env_required("RPC_URL")))

    def get_w3(self) -> Web3:
        return self._w3

    def get_chain_id(self) -> int:
        return self._w3.eth.chain_id

    def get_block_number(self) -> int:
        return self._w3.eth.block_number

    def keccak(self, text: str) -> bytes:
        return self._w3.keccak(text=text)

    def call(self, tx_params: dict, block_identifier: str = "latest") -> str:
        return self._w3.eth.call(tx_params, block_identifier)

    def get_address_from_private_key(self, private_key: PrivateKeyType) -> str:
        return self._w3.eth.account.from_key(private_key).address

    def get_contract(self, contract_address: str, contract_abi_path: str) -> Contract:
        return self._w3.eth.contract(address=contract_address, abi=contract_abi_path)

    def get_transaction_count(self, from_address: str, block_identifier: str = "pending") -> int:
        return self._w3.eth.get_transaction_count(from_address, block_identifier)

    def get_gas_price(self) -> int:
        return self._w3.eth.gas_price

    def get_transaction(self, tx_hash: HexBytes) -> dict:
        return self._w3.eth.get_transaction(tx_hash)

    def send_raw_transaction(self, signed_tx: SignedTransaction) -> HexBytes:
        return self._w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    def wait_for_transaction_receipt(self, tx_hash: HexBytes, timeout: int = 60 * 15, poll_latency: int = 5) -> dict:
        return self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout, poll_latency=poll_latency)

    def sign_transaction(self, tx_params: dict, from_private_key: PrivateKeyType) -> SignedTransaction:
        return self._w3.eth.account.sign_transaction(tx_params, from_private_key)

    def get_address_nonce(self, from_address: str, block_identifier: str = "pending") -> int:
        try:
            latest_nonce = self.get_transaction_count(from_address, "latest")
            if block_identifier == "latest":
                return latest_nonce

            assert block_identifier == "pending", f"Unsupported block identifier: {block_identifier}"
            try:
                pending_nonce = self.get_transaction_count(from_address, "pending")
            except Web3RPCError as e:
                if "actor not found" in str(e):
                    return 0
                raise

            while pending_nonce > latest_nonce:
                while pending_nonce > latest_nonce:
                    # update pending_nonce loop
                    click.echo(f"Address {from_address} has {pending_nonce - latest_nonce} pending transaction(s), waiting...")
                    latest_nonce = self.get_transaction_count(from_address, "latest")

                    time.sleep(5)

                # update pending_nonce loop
                pending_nonce = self.get_transaction_count(from_address, "pending")

            return pending_nonce

        except Exception as e:
            raise Exception(f"Failed to get nonce for address {from_address}: {str(e)}") from e
            
        
