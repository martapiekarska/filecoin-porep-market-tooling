import json
import logging
import time

import click
from eth_account.datastructures import SignedTransaction
from web3 import Web3
from web3.types import RPCEndpoint

from cli import utils
from cli._cli import is_dry_run


# TODO LATER use inbuilt eth_typing / web3 Address type?
class Address(str):
    ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

    def __new__(cls, addr: str):
        return super().__new__(cls, str(Web3.to_checksum_address(addr)))

    def __eq__(self, other):
        try:
            other = Address(other)
        except Exception:
            # nop
            pass

        return super().__eq__(other)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __bool__(self):
        return super() and self != Address.ZERO_ADDRESS

    def __neg__(self):
        return not self.__bool__()

    def __hash__(self):
        return super().__hash__()

    @staticmethod
    def is_filecoin_address(addr: str) -> bool:
        return addr.startswith(("f0", "f1", "f2", "f3", "f4", "f5", "t"))

    @staticmethod
    def from_filecoin_address(addr: str) -> "Address":
        if not Address.is_filecoin_address(addr):
            raise ValueError(f"Invalid Filecoin address format: {addr}")

        response = ContractService.get_w3().provider.make_request(
            RPCEndpoint("Filecoin.FilecoinAddressToEthAddress"),
            [addr]
        )

        if "error" in response:
            raise Exception(response["error"])

        if not response["result"] or not Web3.is_address(response["result"]):
            raise ValueError(f"Invalid response for FilecoinAddressToEthAddress: {response['result']}")

        return Address(response["result"])


class ContractService:
    def __init__(self, contract_address: Address | str, contract_abi_path: str):
        self.logger = logging.getLogger(self._get_class_name())

        with open(contract_abi_path, "r", encoding="utf-8") as abi_file:
            contract_abi = json.load(abi_file)

            self.w3 = ContractService.get_w3()
            self.contract = self.w3.eth.contract(address=Address(str(contract_address)), abi=contract_abi)

    def _get_class_name(self):
        return self.__class__.__name__

    def _send_signed_tx(self, signed_tx: SignedTransaction, dry_run: bool = False) -> str:
        if dry_run:
            return "0x" + "00" * 32

        return self.w3.eth.send_raw_transaction(signed_tx.raw_transaction).to_0x_hex()

    def _sign_and_send_tx(self, transaction, tx_params, from_private_key: str, dry_run: bool = False) -> str:
        # transaction.args is sensitive info, should never be logged
        # tx_params.data is sensitive info, should never be logged

        def tx_to_log_string(transaction, tx_params) -> str:
            result = {
                "chainId": tx_params["chainId"],
                "from": tx_params["from"],
                "to": tx_params["to"],
                "signature": transaction.signature,
                "nonce": tx_params["nonce"],
                "gas": tx_params["gas"],
                "value": tx_params["value"],
            }

            return utils.json_pretty(result)

        try:
            signed_tx = self.w3.eth.account.sign_transaction(tx_params, from_private_key)
        except Exception as e:
            raise Exception(f"Transaction signing failed: {str(e)}") from e

        try:
            tx_hash = self._send_signed_tx(signed_tx, dry_run)
            self.logger.warning(f"Transaction sent: {tx_hash}: {tx_to_log_string(transaction, tx_params)}")
            return tx_hash
        except Exception as e:
            self.logger.error(f"Transaction failed: {str(e)}: {tx_to_log_string(transaction, tx_params)}")
            raise Exception(f"Transaction failed: {str(e)}") from e

    @staticmethod
    def get_w3() -> Web3:
        return Web3(Web3.HTTPProvider(utils.get_env("RPC_URL")))

    @staticmethod
    def get_chain_id() -> int:
        return ContractService.get_w3().eth.chain_id

    @staticmethod
    def get_address_nonce(from_address: Address, w3: Web3 | None = None) -> int:
        try:
            w3 = w3 if w3 else ContractService.get_w3()
            assert w3

            latest_nonce = w3.eth.get_transaction_count(from_address, "latest")
            pending_nonce = w3.eth.get_transaction_count(from_address, "pending")

            while pending_nonce > latest_nonce:
                while pending_nonce > latest_nonce:
                    # update pending_nonce loop
                    click.echo(f"Address {from_address} has {pending_nonce - latest_nonce} pending transaction(s), waiting...")
                    # TODO LATER timeout for fetching nonce
                    latest_nonce = w3.eth.get_transaction_count(from_address, "latest")

                    time.sleep(3)

                # update pending_nonce loop
                pending_nonce = w3.eth.get_transaction_count(from_address, "pending")

            return pending_nonce

        except Exception as e:
            raise Exception(f"Failed to get nonce for address {from_address}: {str(e)}") from e

    def sign_and_send_tx(self, transaction, from_private_key: str) -> str:
        # transaction.args is sensitive info, should never be logged

        from_address = self.w3.eth.account.from_key(from_private_key).address
        nonce = ContractService.get_address_nonce(from_address, self.w3)

        # tx_params.data is sensitive info, should never be logged
        tx_params = transaction.build_transaction({"from": from_address, "nonce": nonce})

        _dry_run = is_dry_run()

        if not utils.ask_user_confirm(f"\n== DRY RUN: {_dry_run}\n"
                                      f"== Chain ID: {tx_params['chainId']}\n"
                                      f"== Transaction:\n"
                                      f"==   from: {tx_params['from']}\n"
                                      f"==   to: {tx_params['to']}\n"
                                      f"==   signature: {transaction.signature}\n"
                                      f"==   nonce: {tx_params['nonce']}\n"
                                      f"==   gas price: {self.w3.eth.gas_price} wei\n"
                                      f"==   gas: {tx_params['gas']}\n"
                                      f"==   value: {tx_params['value']} wei\n"
                                      f"== This is the final confirmation", default_answer=_dry_run):
            click.echo("Enabling dry-run mode. This transaction WILL NOT be executed.")
            _dry_run = True

        click.echo()
        return self._sign_and_send_tx(transaction, tx_params, from_private_key, _dry_run)
