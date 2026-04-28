from ens.utils import Web3
from typing import Dict

from web3.types import RPCEndpoint

from cli import utils
from cli.services.web3_service import Web3Service


def state_get_allocations(actor_id: int) -> Dict[str, dict]:
    method = "Filecoin.StateGetAllocations"
    response = Web3Service().get_w3().provider.make_request(
        RPCEndpoint(method),
        [utils.int_id_to_f0_str(actor_id), None]
    )

    if "error" in response:
        raise RuntimeError(response["error"])

    return response["result"]

def state_lookup_id(address: str) -> int:
    method = "Filecoin.StateLookupID"
    response = Web3Service().get_w3().provider.make_request(RPCEndpoint(method), [address, None])

    if "error" in response:
        raise RuntimeError(response["error"])

    if not response["result"]:
        raise RuntimeError(f"Failed to get actor ID for address {address}: empty result")

    return utils.f0_str_id_to_int(response["result"])

def eth_address_to_filecoin_address(address: str) -> str:
    method = "Filecoin.EthAddressToFilecoinAddress"
    response = Web3Service().get_w3().provider.make_request(RPCEndpoint(method), [address])

    if "error" in response:
        raise RuntimeError(response["error"])

    return response["result"]

def from_filecoin_address_to_eth_address(addr: str) -> str:
    method = "Filecoin.FilecoinAddressToEthAddress"
    response = Web3Service().get_w3().provider.make_request(RPCEndpoint(method), [addr])

    if "error" in response:
        raise RuntimeError(response["error"])

    if not response["result"] or not Web3.is_address(response["result"]):
        raise ValueError(f"Invalid response for FilecoinAddressToEthAddress: {response['result']}")

    return response["result"]
