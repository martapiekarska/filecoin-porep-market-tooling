import json
import time
import click
import logging

from eth_account.datastructures import SignedTransaction
from web3 import Web3
from web3.types import RPCEndpoint
from cli import utils
from cli._cli import is_dry_run


class Address(str):
    ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'

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
        return addr.startswith('f') or addr.startswith('t')

    @staticmethod
    def from_filecoin_address(addr: str) -> 'Address':
        if not Address.is_filecoin_address(addr):
            raise ValueError(f"Not a filecoin address: {addr}")

        w3 = Web3(Web3.HTTPProvider(utils.get_env('RPC_URL')))
        response = w3.provider.make_request(
            RPCEndpoint("Filecoin.FilecoinAddressToEthAddress"),
            [addr]
        )

        if "error" in response:
            raise Exception(response["error"])

        if not response["result"] or not Web3.is_address(response["result"]):
            raise ValueError(f"Invalid response for FilecoinAddressToEthAddress: {response['result']}")

        # noinspection PyTypeChecker
        return Address(response["result"])


class ContractService:
    def __init__(self, contract_address: Address | str, contract_abi_path: str, rpc_url=None):
        rpc_url = rpc_url or utils.get_env('RPC_URL')
        self.logger = logging.getLogger(self._get_class_name())

        with open(contract_abi_path, 'r') as abi_file:
            contract_abi = json.load(abi_file)

            self.w3 = Web3(Web3.HTTPProvider(rpc_url))

            # noinspection PyTypeChecker
            self.contract = self.w3.eth.contract(address=Address(contract_address), abi=contract_abi)

    def _get_class_name(self):
        return self.__class__.__name__

    def _send_tx(self, signed_tx: SignedTransaction, dry_run: bool) -> str:
        if dry_run: return "0x" + "00" * 32
        return self.w3.eth.send_raw_transaction(signed_tx.raw_transaction).to_0x_hex()

    def _sign_and_send_tx(self, transaction, from_private_key: str, dry_run: bool) -> str:
        try:
            signed_tx = self.w3.eth.account.sign_transaction(transaction, from_private_key)
        except Exception as e:
            raise Exception(f"Transaction signing failed: {str(e)}")

        try:
            tx_hash = self._send_tx(signed_tx, dry_run)
            self.logger.info(f"Transaction sent: {transaction}: {tx_hash}")
            return tx_hash
        except Exception as e:
            self.logger.error(f"Transaction failed: {transaction}: {str(e)}")
            raise Exception(f"Transaction failed: {str(e)}")

    @staticmethod
    def get_address_nonce(from_address: Address, w3: Web3) -> int:
        try:
            latest_nonce = w3.eth.get_transaction_count(from_address, 'latest')
            pending_nonce = w3.eth.get_transaction_count(from_address, 'pending')

            while pending_nonce > latest_nonce:
                while pending_nonce > latest_nonce:
                    # update pending_nonce loop
                    click.echo(f"Address {from_address} has {pending_nonce - latest_nonce} pending transaction(s), waiting...")
                    latest_nonce = w3.eth.get_transaction_count(from_address, 'latest')

                    time.sleep(3)

                # update pending_nonce loop
                pending_nonce = w3.eth.get_transaction_count(from_address, 'pending')

            return pending_nonce

        except Exception as e:
            raise Exception(f"Failed to get nonce for address {from_address}: {str(e)}")

    def sign_and_send_tx(self, _transaction, from_private_key: str) -> str:
        from_address = self.w3.eth.account.from_key(from_private_key).address
        nonce = ContractService.get_address_nonce(from_address, self.w3)
        transaction = _transaction.build_transaction({'from': from_address, 'nonce': nonce})

        self.logger.info(f"Transaction prepared: {_transaction.__dict__}")
        _dry_run = is_dry_run()

        if not utils.ask_user_confirm(f"\n== DRY RUN: {_dry_run}\n"
                                      f"== From: {transaction['from']}\n"
                                      f"== To: {transaction['to']}\n"
                                      f"== Signature: {_transaction.signature}\n"
                                      f"== Args: {_transaction.args}\n"
                                      f"== Gas Price: {self.w3.eth.gas_price} wei\n"
                                      f"== Gas: {transaction['gas']}\n"
                                      f"== Value: {transaction['value']} wei\n"
                                      f"This is the final confirmation", default_answer=_dry_run):
            _dry_run = True

        click.echo()
        return self._sign_and_send_tx(transaction, from_private_key, _dry_run)
