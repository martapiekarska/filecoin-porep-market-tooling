from urllib.parse import ParseResult
from requests.compat import urlunparse
import ipaddress
import socket
from requests.compat import urlparse
import click
import requests
from eth_account.types import PrivateKeyType

from cli import utils
from cli._cli import is_dry_run
from cli.services.contracts.contract_service import Address, ContractService
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealProposal, PoRepMarket

# TODO LATER take sector size from smart contracts
SECTOR_SIZE_BYTES = 32 * 1024 ** 3  # 32 GiB

@utils.json_dataclass()
class ManifestPiece:
    id: int
    createdAt: str
    pieceType: str       
    pieceCid: str         
    pieceSize: int       
    rootCid: str
    fileSize: int
    minPieceSizePadding: int
    storageId: int
    storagePath: str
    numOfFiles: int
    preparationId: int
    attachmentId: int
    jobId: int

@utils.json_dataclass()
class DealManifestConfig:
    case_insensitive: str
    case_sensitive: str
    copy_links: str
    description: str
    encoding: str
    hashes: str
    links: str
    no_check_updated: str
    no_clone: str
    no_preallocate: str
    no_set_modtime: str
    no_sparse: str
    nounc: str
    one_file_system: str
    skip_links: str
    skip_specials: str
    time_type: str
    unicode_normalization: str
    zero_size_links: str

@utils.json_dataclass()
class DealManifestSource:
    id: int
    name: str
    createdAt: str
    updatedAt: str
    type: str
    path: str
    config: DealManifestConfig
    clientConfig: dict

@utils.json_dataclass()
class _DealManifest:
    attachmentId: int
    storageId: int
    source: DealManifestSource
    pieces: list[ManifestPiece]


DealManifest = list[_DealManifest]

def bytes_to_sectors(bytes_size: int) -> float:
    return bytes_size / SECTOR_SIZE_BYTES


def get_all_deals(state: PoRepMarketDealState | str | None = None,
                  organization: Address | None = None) -> list[PoRepMarketDealProposal]:
    #
    _state = PoRepMarketDealState.from_string(str(state)) if state else None

    if organization:
        # prefer get_deals_for_organization_by_state function when asking for organization...
        result = []
        selected_states = [_state] if _state else list(PoRepMarketDealState)

        for selected_state in selected_states:
            result.extend(PoRepMarket().get_deals_for_organization_by_state(organization, selected_state))
    else:
        # ... otherwise prefer get_all_deals function
        result = PoRepMarket().get_all_deals()

        if _state:
            result = [deal for deal in result if deal.state == _state]

    return result


def print_info():
    try:
        click.echo(f"Chain ID: {ContractService.get_chain_id()}")
    except Exception as e:
        click.echo(f"Error getting chain ID: {e}\n")

    click.echo(f"RPC_URL={utils.get_env('RPC_URL', required=False)}")
    click.echo()
    click.echo(f"POREP_MARKET={utils.get_env('POREP_MARKET', required=False)}")
    click.echo(f"CLIENT_CONTRACT={utils.get_env('CLIENT_CONTRACT', required=False)}")
    click.echo(f"SP_REGISTRY={utils.get_env('SP_REGISTRY', required=False)}")
    click.echo(f"VALIDATOR_FACTORY={utils.get_env('VALIDATOR_FACTORY', required=False)}")
    click.echo(f"FILECOIN_PAY={utils.get_env('FILECOIN_PAY', required=False)}")
    click.echo(f"USDC_TOKEN={utils.get_env('USDC_TOKEN', required=False)}")
    click.echo()
    click.echo(f"DRY_RUN={is_dry_run()}")
    click.echo(f"DEBUG={utils.get_env_required('DEBUG', default='False').capitalize()}")


def validate_address_matches_private_key(address: Address, private_key: PrivateKeyType | None):
    if not private_key:
        raise Exception("Private key is not set")

    derived_address = Address.from_private_key(private_key)

    if derived_address != address:
        raise Exception(f"Address {address} does not match private key {utils.private_str_to_log_str(private_key)} (expected: {derived_address})")


# retries = None means "ask user"
def fetch_manifest(manifest_url: str, show_manifest: bool | None = None, retries: int | None = None, quiet: bool = False) -> DealManifest:
    if not quiet:
        click.echo(f"Fetching manifest from {manifest_url}")

    parsed_url = _get_manifest_hostname(manifest_url)

    while True:
        try:
            return _fetch_manifest(parsed_url, show_manifest, quiet)
        except requests.exceptions.RequestException as e:
            if retries is None:
                if not utils.ask_user_confirm(f"\nFailed to fetch manifest:\n{e}.\nRetry?", default_answer=True):
                    raise Exception(f"Network error while fetching manifest: {e}") from e

            else:
                if retries <= 0:
                    raise Exception(f"Network error while fetching manifest: {e}") from e
                else:
                    if not quiet:
                        click.echo(f"Retrying... ({retries} retries left)")

                    retries -= 1


def _get_manifest_hostname(manifest_url: str) -> ParseResult:
    parsed = urlparse(manifest_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Manifest URL must use http/https")

    ip = socket.gethostbyname(parsed.hostname)
    addr = ipaddress.ip_address(ip)
    if addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local or addr.is_multicast:
        raise ValueError(f"Manifest URL resolves to a disallowed IP address: {ip}")

    return parsed


def _fetch_manifest(parsed_url: ParseResult, show_manifest: bool | None = None, quiet: bool = False) -> DealManifest:
    MINIMUM_DAG_PIECE_SIZE_BYTES = 1024 * 1024  # 1 MiB

    # download manifest
    ip = socket.gethostbyname(parsed_url.hostname)
    netloc = f"{ip}:{parsed_url.port}" if parsed_url.port else ip
    ip_url = urlunparse(parsed_url._replace(netloc=netloc))
    resp = requests.get(ip_url, headers={"Host": parsed_url.hostname}, timeout=30)
    resp.raise_for_status()

    try:
        manifest = resp.json()
    except ValueError as e:
        raise ValueError(f"Manifest is not a valid JSON: {e}") from e

    if not quiet:
        click.echo("Manifest downloaded")

    # show manifest
    if show_manifest or (show_manifest is None and utils.ask_user_confirm("Show manifest?", default_answer=False)):
        _manifest = utils.json_pretty(manifest)
        click.echo_via_pager("\n".join([f"{i + 1}. {line}" for i, line in enumerate(_manifest.splitlines())]))
        click.echo()

    try:
        # validate manifest format
        if not (
                manifest and
                isinstance(manifest, list) and
                len(manifest) == 1 and

                manifest[0] and
                isinstance(manifest[0], dict) and
                "pieces" in manifest[0] and

                manifest[0]["pieces"] and
                isinstance(manifest[0]["pieces"], list) and

                all(isinstance(piece, dict) and
                    "pieceCid" in piece and
                    "pieceType" in piece and
                    "pieceSize" in piece and
                    "preparationId" in piece and
                    "attachmentId" in piece and
                    "storagePath" in piece
                    for piece in manifest[0]["pieces"])
        ):
            raise ValueError("Invalid manifest format")

        # validate manifest pieces
        pieces = manifest[0]["pieces"]
        data_pieces = [piece for piece in pieces if piece["pieceType"] == "data"]
        dag_pieces = [piece for piece in pieces if piece["pieceType"] == "dag"]

        if len(pieces) <= 1 or len(data_pieces) != len(pieces) - 1 or len(dag_pieces) != 1:
            raise ValueError("Invalid manifest pieces: must contain exactly one dag piece and at least one data piece")

        if not all(piece["preparationId"] == pieces[0]["preparationId"] for piece in pieces):
            raise ValueError("Invalid preparationId in manifest pieces: must be the same for all pieces")

        if not all(piece["attachmentId"] == pieces[0]["attachmentId"] for piece in pieces):
            raise ValueError("Invalid attachmentId in manifest pieces: must be the same for all pieces")

        if dag_pieces[0]["pieceSize"] < MINIMUM_DAG_PIECE_SIZE_BYTES:
            raise ValueError(f"Invalid dag piece size in manifest: must be at least 1 MiB "
                             f"({dag_pieces[0]['pieceSize']} < {MINIMUM_DAG_PIECE_SIZE_BYTES} bytes)")
        #
    except KeyError as e:
        raise ValueError(f"Invalid manifest format: missing key {e}") from e
    
    # TODO return DealManifest type here
    return manifest
