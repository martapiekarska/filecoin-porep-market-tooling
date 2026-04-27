# pylint: disable=broad-exception-caught

import json
import logging
import time

import click
import eth_abi
from eth_account.datastructures import SignedTransaction
from eth_account.types import PrivateKeyType
from eth_typing import ABIElement
from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import ContractCustomError, Web3RPCError
from web3.types import RPCEndpoint

from cli import utils
from cli._cli import is_dry_run


class Address(str):
    ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

    def __new__(cls, addr: str) -> "Address":
        # noinspection PyTypeChecker
        return super().__new__(cls, str(Web3.to_checksum_address(addr)))

    def __eq__(self, other):
        # noinspection PyBroadException
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

    def to_filecoin_address(self) -> str:
        method = "Filecoin.EthAddressToFilecoinAddress"
        response = ContractService.get_w3().provider.make_request(RPCEndpoint(method), [self])

        if "error" in response:
            raise RuntimeError(response["error"])

        return response["result"]

    def to_actor_id(self) -> int:
        method = "Filecoin.StateLookupID"
        response = ContractService.get_w3().provider.make_request(RPCEndpoint(method), [self.to_filecoin_address(), None])

        if "error" in response:
            raise RuntimeError(response["error"])

        if not response["result"]:
            raise RuntimeError(f"Failed to get actor ID for address {self}: empty result")

        return utils.f0_str_id_to_int(response["result"])

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
            raise RuntimeError(response["error"])

        if not response["result"] or not Web3.is_address(response["result"]):
            raise ValueError(f"Invalid response for FilecoinAddressToEthAddress: {response['result']}")

        return Address(response["result"])

    @staticmethod
    def from_private_key(private_key: PrivateKeyType) -> "Address":
        try:
            return Address(ContractService.get_w3().eth.account.from_key(private_key).address)
        except Exception as e:
            raise ValueError(f"Invalid private key: {str(e)}") from e


class ContractService:
    ZERO_TX_HASH = "0x" + "00" * 32

    def __init__(self, contract_address: Address, contract_abi_path: str):
        self.logger = logging.getLogger(self._get_class_name())

        with open(contract_abi_path, "r", encoding="utf-8") as abi_file:
            contract_abi = json.load(abi_file)

            self.w3 = ContractService.get_w3()
            self.contract = self.w3.eth.contract(address=Address(str(contract_address)), abi=contract_abi)

    def _get_class_name(self):
        return self.__class__.__name__

    def filecoin_address(self) -> str:
        return Address(self.contract.address).to_filecoin_address()

    def actor_id(self) -> int:
        return Address(self.contract.address).to_actor_id()

    def __decode_contract_error_name(self, err: ContractCustomError) -> str:
        def find_error_in_abi(selector: bytes) -> ABIElement | None:
            for item in [i for i in self.contract.abi if i.get("type") == "error"]:
                sig = item["name"] + "(" + ",".join(i["type"] for i in item["inputs"]) + ")"

                if self.w3.keccak(text=sig)[:4] == selector:
                    return item

            return None

        def format_error_args(abi_error: ABIElement, arg_data: bytes) -> str:
            types = [i["type"] for i in abi_error["inputs"]]
            names = [i["name"] for i in abi_error["inputs"]]
            decoded = eth_abi.decode(types, arg_data)

            return ", ".join(f"{n}={v}" for n, v in zip(names, decoded))

        if not err.data:
            return str(err)

        if isinstance(err.data, str):
            raw = bytes.fromhex(err.data.removeprefix("0x"))
        elif isinstance(err.data, (bytes, bytearray)):
            raw = bytes(err.data)
        else:
            return str(err)

        if len(raw) < 4:
            return str(err)

        hex_data = "0x" + raw.hex()
        selector, arg_data = raw[:4], raw[4:]

        abi_error = find_error_in_abi(selector)

        if not abi_error:
            return f"UnknownError hex={hex_data}"

        if not abi_error["inputs"]:
            return f"{abi_error['name']}"

        # noinspection PyBroadException
        try:
            return f"{abi_error['name']}({format_error_args(abi_error, arg_data)})"
        except Exception:
            return f"DecodingError name={abi_error['name']} hex={hex_data} err={str(err)}"

    def __send_tx(self, signed_tx: SignedTransaction, dry_run: bool) -> HexBytes:
        assert not dry_run
        return self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    def _sign_and_send_tx(self, transaction, tx_params: dict, from_private_key: PrivateKeyType, dry_run: bool = False) -> str:
        # transaction.args is sensitive info, should never be logged
        # tx_params.data is sensitive info, should never be logged

        signed_tx = self.w3.eth.account.sign_transaction(tx_params, from_private_key)

        if dry_run:
            return ContractService.ZERO_TX_HASH

        # NOT DRY RUN, SENDING TRANSACTION

        tx_hash = self.__send_tx(signed_tx, dry_run)
        self.logger.warning(f"Transaction sent: {tx_hash.to_0x_hex()}: {ContractService.tx_to_log_string(transaction, tx_params)}")

        click.echo(f"Waiting for transaction {tx_hash.to_0x_hex()}...")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60 * 15, poll_latency=5)  # 15 minutes timeout, 5 seconds polling interval

        if receipt["status"] == 0:
            # tx failed
            tx = self.w3.eth.get_transaction(tx_hash)

            # this call should revert with the same error as the transaction
            reason = self.w3.eth.call({"to": tx["to"], "from": tx["from"], "data": tx["input"]}, receipt["blockNumber"])
            raise click.ClickException(f"Transaction reverted (reason unknown, call returned: {reason.hex() if reason else 'empty'})")

        # tx succeeded
        self.logger.warning(f"Transaction succeeded: {tx_hash.to_0x_hex()}: {ContractService.tx_to_log_string(transaction, tx_params)}")
        return tx_hash.to_0x_hex()

    def sign_and_send_tx(self, transaction, from_private_key: PrivateKeyType) -> str:
        # transaction.args is sensitive info, should never be logged

        from_address = Address.from_private_key(from_private_key)
        nonce = ContractService.get_address_nonce(from_address, self.w3)
        tx_params = None

        try:
            # tx_params.data is sensitive info, should never be logged
            tx_params = transaction.build_transaction({"from": from_address, "nonce": nonce})

            _dry_run = is_dry_run()

            if not click.confirm(f"\n== DRY RUN: {_dry_run}\n"
                                 f"== Chain ID: {tx_params['chainId']}\n"
                                 f"== Transaction:\n"
                                 f"==   from: {tx_params['from']}\n"
                                 f"==   to: {tx_params['to']}\n"
                                 f"==   signature: {transaction.signature}\n"
                                 f"==   nonce: {tx_params['nonce']}\n"
                                 f"==   gas price: {self.w3.eth.gas_price} wei\n"
                                 f"==   gas: {tx_params['gas']}\n"
                                 f"==   value: {tx_params['value']} wei\n"
                                 f"== This is the final confirmation", default=_dry_run):
                click.echo("Enabling dry-run mode. This transaction WILL NOT be executed.")
                _dry_run = True

            click.echo()
            return self._sign_and_send_tx(transaction, tx_params, from_private_key, _dry_run)
        except ContractCustomError as cce:
            reason = self.__decode_contract_error_name(cce)
            self.logger.error(f"Transaction reverted with error: {reason}: {ContractService.tx_to_log_string(transaction, tx_params)}")
            raise click.ClickException(f"Transaction reverted with error: {reason}") from cce
        except Web3RPCError as rpc_err:
            reason = rpc_err.rpc_response["error"]["message"] if (rpc_err.rpc_response and
                                                                  "error" in rpc_err.rpc_response and
                                                                  "message" in rpc_err.rpc_response["error"] and
                                                                  rpc_err.rpc_response["error"]["message"]) else str(rpc_err)

            self.logger.error(f"Web3 RPC error: {reason}: {ContractService.tx_to_log_string(transaction, tx_params)}")
            raise click.ClickException(f"Web3 RPC error: {reason}") from rpc_err
        except Exception as e:
            reason = str(e)
            self.logger.error(f"Transaction failed: {reason}: {ContractService.tx_to_log_string(transaction, tx_params)}")
            raise click.ClickException(f"Transaction failed: {reason}") from e

    @staticmethod
    def tx_to_log_string(transaction, tx_params: dict | None) -> str:
        # transaction.args is sensitive info, should never be logged
        # tx_params.data is sensitive info, should never be logged

        result = {
            "chainId": tx_params["chainId"],
            "from": tx_params["from"],
            "to": tx_params["to"],
            "signature": transaction.signature,
            "nonce": tx_params["nonce"],
            "gas": tx_params["gas"],
            "value": tx_params["value"],
        } if tx_params else {
            "to": transaction.address,
            "signature": transaction.signature,
        }

        return utils.json_pretty(result)

    @staticmethod
    def get_w3() -> Web3:
        return Web3(Web3.HTTPProvider(utils.get_env_required("RPC_URL")))

    @staticmethod
    def get_chain_id() -> int:
        return ContractService.get_w3().eth.chain_id

    @staticmethod
    def get_block_number() -> int:
        return ContractService.get_w3().eth.block_number

    @staticmethod
    def wait_for_pending_transactions(from_address: Address, w3: Web3 | None = None):
        _ = ContractService.get_address_nonce(from_address, w3, block_identifier="pending")

    @staticmethod
    def get_address_nonce(from_address: Address,
                          w3: Web3 | None = None,
                          block_identifier: str = "pending") -> int:
        try:
            w3 = w3 if w3 else ContractService.get_w3()
            assert w3

            latest_nonce = w3.eth.get_transaction_count(from_address, "latest")
            if block_identifier == "latest":
                return latest_nonce

            assert block_identifier == "pending", f"Unsupported block identifier: {block_identifier}"
            pending_nonce = w3.eth.get_transaction_count(from_address, "pending")

            while pending_nonce > latest_nonce:
                while pending_nonce > latest_nonce:
                    # update pending_nonce loop
                    click.echo(f"Address {from_address} has {pending_nonce - latest_nonce} pending transaction(s), waiting...")
                    latest_nonce = w3.eth.get_transaction_count(from_address, "latest")

                    time.sleep(5)

                # update pending_nonce loop
                pending_nonce = w3.eth.get_transaction_count(from_address, "pending")

            return pending_nonce

        except Web3RPCError as rpc_err:
            reason = rpc_err.rpc_response["error"]["message"] if (rpc_err.rpc_response and
                                                                  "error" in rpc_err.rpc_response and
                                                                  "message" in rpc_err.rpc_response["error"] and
                                                                  rpc_err.rpc_response["error"]["message"]) else str(rpc_err)

            raise RuntimeError(f"Web3 RPC error while getting nonce for address {from_address}: {reason}") from rpc_err

        except Exception as e:
            raise RuntimeError(f"Failed to get nonce for address {from_address}: {str(e)}") from e
