from typing import Dict

from web3.types import RPCEndpoint

from cli import utils
from cli.services.contracts.contract_service import ContractService


def state_get_allocations(actor_id: int) -> Dict[str, dict]:
    method = "Filecoin.StateGetAllocations"
    response = ContractService.get_w3().provider.make_request(
        RPCEndpoint(method),
        [utils.int_id_to_f0_str(actor_id), None]
    )

    if "error" in response:
        raise RuntimeError(response["error"])

    return response["result"]
