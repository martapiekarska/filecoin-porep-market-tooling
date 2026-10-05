import base64
import ipaddress
import json
import logging
import os
import re
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

import click
import requests
from web3.types import RPCEndpoint

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealType
from cli.services.contracts.porep_market_view_helper import PoRepMarketDealView, PoRepMarketViewHelper
from cli.services.contracts.sp_registry import SPRegistry
from cli.services.web3_service import ActorId, EthAddress, Web3Service

# Shared code for the FCSS repair flow, used by the client commands and `sp onboard-data`:
# - finding a "healthy" SP still serving a dataset, and the large-paid-retrievals (LPR) price it charges,
# - resolving the payee and token the repair retrieval is paid with (the same for client and SP),
# - legacy (v1) repair manifests with an embedded source,
# - small helpers: Decimal price options, child process environments, secret file checks.
#
# Healthy = another provider's deal for the same dataset (same manifest hash) that is ACTIVE, PUBLIC (LPR only lets
# deal owners retrieve private deals) and has claims on-chain, AND whose advertised HTTP piece endpoint actually serves
# sample pieces of the expected size. The price comes from the LPR sp-proxy `402` challenge for those pieces
# (https://github.com/fidlabs/large-paid-retrievals/blob/main/docs/mpp-filecoinpay.md); a `200` means free.

logger = logging.getLogger(__name__)

GIB_BYTES = 2 ** 30
CID_CONTACT_URL = "https://cid.contact"
PROBE_SAMPLE_PIECES = 2
PROBE_TIMEOUT_SECONDS = 30

# multiaddr protocol codes needed to find HTTP endpoints: code -> (name, value size in bytes, 0 = none, -1 = varint-prefixed)
_MULTIADDR_PROTOCOLS = {4: ("ip4", 4), 41: ("ip6", 16), 53: ("dns", -1), 54: ("dns4", -1), 55: ("dns6", -1), 6: ("tcp", 2),
                        480: ("http", 0), 443: ("https", 0), 448: ("tls", 0), 477: ("ws", 0), 478: ("wss", 0), 421: ("p2p", -1)}

# /<host proto>/<host>/tcp/<port>/<transport>; Curio advertises its market HTTP server as libp2p (w)ss on the same host:port
_HTTP_MULTIADDR = re.compile(r"^/(?:ip4|ip6|dns|dns4|dns6)/([^/]+)/tcp/(\d+)/(http|https|tls/http|wss|ws)(?:/|$)")


AMOUNT_PRECISION = 100  # significant digits for repair price arithmetic; uint256 has at most 78


# Repair prices are parsed from the user's text as Decimal, never as binary floats
class DecimalAmount(click.ParamType):
    name = "decimal"

    def __init__(self, min_value: Decimal | int = 0, min_open: bool = False):
        self.min_value = Decimal(min_value)
        self.min_open = min_open

    def convert(self, value, param, ctx) -> Decimal:
        if isinstance(value, Decimal):
            result = value
        else:
            try:
                result = Decimal(str(value).strip())
            except InvalidOperation:
                self.fail(f"{value!r} is not a decimal number", param, ctx)

        if not result.is_finite():
            self.fail(f"{value!r} is not a finite number", param, ctx)

        if result < self.min_value or (self.min_open and result == self.min_value):
            self.fail(f"{value} is not {'>' if self.min_open else '>='} {self.min_value}", param, ctx)

        return result


_SECRET_ENV_VAR = re.compile(r"(PRIVATE_KEY|LOTUS_TOKEN|DATABASE_URL)$")


# Environment for external programs: everything except this CLI's secrets (private keys, Lotus tokens, database URLs),
# which they don't need; `keep` names the exceptions.
def child_env(keep: tuple[str, ...] = (), **extra: str) -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if name in keep or not _SECRET_ENV_VAR.search(name)}
    env.update(extra)
    return env


# Like SSH does for private key files: a file holding a secret must be owned by the current user and not be accessible
# by group or others. No-op where POSIX permissions don't apply (Windows).
def secret_file_problem(path: Path) -> str | None:
    if os.name != "posix":
        return None

    stat = path.stat()

    if stat.st_uid != os.getuid():
        return f"{path} is owned by another user (uid {stat.st_uid})"

    if stat.st_mode & 0o077:
        return f"{path} is accessible by other users (mode {oct(stat.st_mode & 0o777)}); run: chmod 600 {path}"

    return None


def ensure_secret_file(path: Path, description: str):
    problem = secret_file_problem(path)

    if problem:
        raise click.ClickException(f"Refusing to use {description}: {problem}")


@utils.json_dataclass()
class PieceProbe:
    status: str  # free | paid | private | unavailable
    size_bytes: int | None = None
    price: Decimal | None = None  # total quoted price for the piece, in decimal tokens
    detail: str | None = None


@utils.json_dataclass()
class RetrievalSource:
    base_url: str
    price_per_gib: Decimal  # 0 when the source serves for free
    deal_id: int | None = None  # None for a manually given source URL
    provider_id: ActorId | None = None

    def is_free(self) -> bool:
        return self.price_per_gib == 0


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    result = shift = 0

    while True:
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        shift += 7

        if not byte & 0x80:
            return result, offset


# minimal binary -> text multiaddr decoding for Filecoin.StateMinerInfo Multiaddrs; returns None on unsupported protocols
def multiaddr_to_string(raw: bytes) -> str | None:
    parts = []
    offset = 0

    try:
        while offset < len(raw):
            code, offset = _read_varint(raw, offset)

            if code not in _MULTIADDR_PROTOCOLS:
                return None

            name, size = _MULTIADDR_PROTOCOLS[code]
            parts.append(name)

            if size == -1:
                size, offset = _read_varint(raw, offset)
                value = raw[offset:offset + size]
                parts.append(value.decode() if name.startswith("dns") else base64.b32encode(value).decode())
            elif size:
                value = raw[offset:offset + size]
                parts.append(str(ipaddress.ip_address(value)) if name in ("ip4", "ip6") else str(int.from_bytes(value, "big")))

            offset += max(size, 0)

    except (IndexError, ValueError, UnicodeDecodeError):
        return None

    return "/" + "/".join(parts)


def http_base_from_multiaddr(addr: str) -> str | None:
    match = _HTTP_MULTIADDR.match(addr.strip())

    if not match:
        return None

    host, port, transport = match.groups()
    scheme = "https" if transport in ("https", "tls/http", "wss") else "http"
    host = f"[{host}]" if ":" in host else host
    return f"{scheme}://{host}:{port}"


# Like LPR retrieval-client's discovery (pieceurls): miner PeerId -> cid.contact provider addrs, else on-chain miner multiaddrs.
# Unlike LPR, Curio's (w)ss market address is also mapped to http(s) on the same host:port (see _HTTP_MULTIADDR).
def discover_provider_http_bases(provider_id: ActorId) -> list[str]:
    response = Web3Service().w3().provider.make_request(RPCEndpoint("Filecoin.StateMinerInfo"), [str(provider_id), None])

    if "error" in response or not response.get("result"):
        raise RuntimeError(f"Filecoin.StateMinerInfo({provider_id}) failed: {response.get('error')}")

    miner_info = response["result"]
    addrs: list[str] = []

    if miner_info.get("PeerId"):
        try:
            resp = requests.get(f"{CID_CONTACT_URL}/providers/{miner_info['PeerId']}", timeout=PROBE_TIMEOUT_SECONDS)
            if resp.ok:
                addrs = re.findall(r'"(/[^"]+)"', resp.text)

        # best effort, fall back to on-chain multiaddrs
        except requests.RequestException as e:
            logger.warning("cid.contact lookup for %s failed: %s", provider_id, e)

    bases = [base for base in (http_base_from_multiaddr(addr) for addr in addrs) if base]

    if not bases:
        decoded = (multiaddr_to_string(base64.b64decode(addr)) for addr in miner_info.get("Multiaddrs") or [])
        bases = [base for base in (http_base_from_multiaddr(addr) for addr in decoded if addr) if base]

    return list(dict.fromkeys(bases))


def _parse_payment_challenge(www_authenticate: str) -> dict:
    match = re.search(r'request="([^"]+)"', www_authenticate)

    if not www_authenticate.startswith("Payment") or not match:
        raise ValueError(f"not an MPP Payment challenge: {www_authenticate!r}")

    encoded = match.group(1)
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def probe_piece(base_url: str, piece_cid: str) -> PieceProbe:
    url = f"{base_url}/piece/{piece_cid}"

    try:
        commands_utils.validate_and_parse_url(url)  # SSRF guard: endpoints are advertised by SPs
    except (click.ClickException, OSError) as e:
        return PieceProbe(status="unavailable", detail=str(e))

    try:
        head = requests.head(url, timeout=PROBE_TIMEOUT_SECONDS, allow_redirects=False)
        size = int(head.headers.get("Content-Length", 0)) if head.status_code == 200 else None

        # a 1-byte range keeps a free server from streaming the whole piece; LPR sp-proxy answers 402 regardless
        with requests.get(url, headers={"Range": "bytes=0-0"}, timeout=PROBE_TIMEOUT_SECONDS, stream=True, allow_redirects=False) as resp:
            if resp.status_code in (200, 206):
                if size is None and "/" in resp.headers.get("Content-Range", ""):
                    size = int(resp.headers["Content-Range"].rsplit("/", 1)[1])
                return PieceProbe(status="free", size_bytes=size)

            if resp.status_code == 402:
                challenge = _parse_payment_challenge(resp.headers.get("WWW-Authenticate", ""))
                price = Decimal(challenge["price_usdfc"])

                if not price.is_finite() or price < 0:
                    raise ValueError(f"invalid quoted price {challenge['price_usdfc']!r}")

                return PieceProbe(status="paid", size_bytes=size, price=price)

            if resp.status_code == 403:
                return PieceProbe(status="private", detail="403 Forbidden")

            return PieceProbe(status="unavailable", detail=f"HTTP {resp.status_code}")

    # any malformed SP response (bad header, JSON, number, ...) makes the source unavailable rather than crashing the CLI
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, ArithmeticError) as e:
        return PieceProbe(status="unavailable", detail=str(e))


def _sample_pieces(pieces: list[dict]) -> list[dict]:
    return pieces[:PROBE_SAMPLE_PIECES]


# probes sample pieces at base_url; returns the source with its price per GiB, or None with a reason
def probe_source(base_url: str, pieces: list[dict]) -> tuple[RetrievalSource | None, str]:
    prices_per_gib = set()

    for piece in _sample_pieces(pieces):
        probe = probe_piece(base_url, piece["pieceCid"])

        if probe.status in ("private", "unavailable"):
            return None, f"piece {piece['pieceCid']}: {probe.status} ({probe.detail})"

        if probe.size_bytes is not None and probe.size_bytes != piece["fileSize"]:
            return None, f"piece {piece['pieceCid']}: size {probe.size_bytes} != manifest fileSize {piece['fileSize']}"

        if probe.status == "paid":
            if not probe.size_bytes:
                return None, f"piece {piece['pieceCid']}: paid but size unknown"

            # LPR sp-proxy price = price per GiB * GiB rounded up
            with localcontext() as ctx:
                ctx.prec = AMOUNT_PRECISION
                prices_per_gib.add(probe.price / -(-int(probe.size_bytes) // GIB_BYTES))
        else:
            prices_per_gib.add(Decimal(0))

    if len(prices_per_gib) > 1:
        click.echo(f"WARNING: {base_url} quoted inconsistent prices per GiB {sorted(prices_per_gib)}; using the highest")

    return RetrievalSource(base_url=base_url, price_per_gib=max(prices_per_gib)), "ok"


def find_healthy_source(manifest_hash: bytes,
                        pieces: list[dict],
                        exclude_provider_ids: set[ActorId],
                        source_url: str | None = None) -> RetrievalSource:
    #
    if source_url:
        source, reason = probe_source(source_url.rstrip("/"), pieces)
        if not source:
            raise click.ClickException(f"Source {source_url} is not serving the dataset: {reason}")

        click.echo(f"Using source {source.base_url}: {_price_str(source)}")
        return source

    click.echo("\nLooking for a healthy SP still serving this dataset (same manifest, other providers)...")
    candidates = []

    # full deal views in pages of 100: one RPC call per page instead of one per deal
    for view in PoRepMarketViewHelper().get_deal_views():
        if (view.deal.state != PoRepMarketDealState.ACTIVE
                or view.deal.provider_id in exclude_provider_ids
                or view.deal.provider_id in (c.deal.provider_id for c in candidates)):
            continue

        if bytes(view.data.manifest_hash) == bytes(manifest_hash):
            candidates.append(view)

    sources = []

    for view in candidates:
        label = f"  deal {view.deal.deal_id} provider {view.deal.provider_id}"

        if view.deal.deal_type != PoRepMarketDealType.PUBLIC:
            click.echo(f"{label}: skipped, {view.deal.deal_type} deal (LPR only serves private deals to their owner)")
            continue

        if not commands_utils.get_deal_claim_ids(view.deal):
            click.echo(f"{label}: skipped, no claims on-chain")
            continue

        try:
            bases = discover_provider_http_bases(view.deal.provider_id)
        except RuntimeError as e:
            click.echo(f"{label}: skipped, {e}")
            continue

        if not bases:
            click.echo(f"{label}: skipped, no advertised HTTP endpoint")
            continue

        for base_url in bases:
            source, reason = probe_source(base_url, pieces)

            if source:
                source.deal_id, source.provider_id = view.deal.deal_id, view.deal.provider_id
                click.echo(f"{label} at {base_url}: healthy, {_price_str(source)}")
                sources.append(source)
                break

            click.echo(f"{label} at {base_url}: not serving, {reason}")

    if not sources:
        raise click.ClickException("No healthy SP found serving this dataset; pass a source URL explicitly if you know one")

    # same preference as LPR retrieval-client: free first, then cheapest
    return min(sources, key=lambda s: s.price_per_gib)


def _price_str(source: RetrievalSource) -> str:
    return "free" if source.is_free() else f"{source.price_per_gib} tokens/GiB"


# Shared by the client, who funds the repair retrieval, and the new SP, who spends it: both must use the same FileCoinPay
# account (the deal's SP payee) and token (the deal's payment token), or the deposit lands where the retrieval can't use it.
def resolve_repair_payee(deal: PoRepMarketDealView) -> EthAddress:
    payee = deal.payment.payee

    if int(payee, 16) == 0:
        payee = SPRegistry().get_provider_view(deal.deal.provider_id).payee_address

    if int(payee, 16) == 0:
        raise click.ClickException(f"No payee address found for deal ID {deal.deal.deal_id} provider {deal.deal.provider_id}")

    # retrieval-client signs with a plain secp256k1 key, so a contract payee (e.g. multisig) cannot retrieve
    if Web3Service().w3().eth.get_code(payee):
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} payee {payee} is a contract; "
                                   f"the repair retrieval needs an externally owned payee wallet.")

    return EthAddress(payee)


def repair_payment_token(deal: PoRepMarketDealView) -> EthAddress:
    return EthAddress(deal.payment.payment_token)


# Legacy (v1) repair: the client supplies the original manifest and the healthy source; the source is embedded in the
# new deal's manifest under this key, so the new SP's `sp onboard-data` knows where to fetch from with no coordination.
REPAIR_SOURCE_KEY = "repairSource"
_TOADS_DATASET_URL = re.compile(r"^https://toads\.directory/dataset/([0-9a-fA-F-]{36})/?$")


def get_manifest_repair_source(manifest: list[dict]) -> str | None:
    source = manifest[0].get(REPAIR_SOURCE_KEY)
    return source.rstrip("/") if isinstance(source, str) and source else None


# local file, manifest URL, or a toads.directory dataset page URL (resolved through its dataset API)
def load_manifest_json(manifest_input: str) -> object:
    toads_match = _TOADS_DATASET_URL.match(manifest_input)

    if toads_match:
        url = f"https://toads.directory/api/datasets/{toads_match.group(1)}"
    elif manifest_input.startswith(("http://", "https://")):
        url = manifest_input
    else:
        try:
            return json.loads(Path(manifest_input).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise click.ClickException(f"Failed to read manifest file {manifest_input}: {e}") from e

    commands_utils.validate_and_parse_url(url)

    try:
        resp = requests.get(url, timeout=PROBE_TIMEOUT_SECONDS, allow_redirects=False)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        raise click.ClickException(f"Failed to fetch manifest from {url}: {e}") from e

    if toads_match:
        try:
            return data["data"]["manifestData"]
        except (KeyError, TypeError) as e:
            raise click.ClickException(f"No manifest found in toads.directory dataset {url}") from e

    return data


def _padded_piece_size(file_size: int) -> int:
    # smallest power of two holding the FR32-expanded CAR (127 data bytes per 128-byte chunk), at least the 128-byte minimum piece
    return max(128, 1 << (-(-file_size * 128 // 127) - 1).bit_length())


# Converts a data-prep-standard super-manifest whose contents are the pieces' CAR files (as served by toads.directory)
# into this CLI's manifest format. pieceSize is the minimal padded size of each CAR, and the smallest piece is taken to
# be the Singularity DAG piece (only used by `client make-allocations --exclude-dag`).
def _super_manifest_to_manifest(super_manifest: dict) -> list[dict]:
    cars = {entry.get("name"): entry for entry in super_manifest.get("contents") or [] if isinstance(entry, dict)}
    dataset_id = str(super_manifest.get("uuid") or "legacy")
    pieces = []

    for piece in super_manifest.get("pieces") or []:
        car = cars.get(f"{piece.get('piece_cid')}.car")

        if not car or not isinstance(car.get("byte_length"), int) or car.get("piece_cid") != piece["piece_cid"]:
            raise click.ClickException(f"Unsupported super-manifest: no `<piece_cid>.car` contents entry with byte_length "
                                       f"for piece {piece.get('piece_cid')}")

        pieces.append({
            "pieceCid": piece["piece_cid"],
            "pieceType": "data",
            "pieceSize": _padded_piece_size(car["byte_length"]),
            "fileSize": car["byte_length"],
            "preparationId": dataset_id,
            "attachmentId": dataset_id,
            "storagePath": f"{piece['piece_cid']}.car",
        })

    if len(pieces) < 2:
        raise click.ClickException("Unsupported super-manifest: expected a DAG piece and at least one data piece")

    min(pieces, key=lambda p: p["fileSize"])["pieceType"] = "dag"
    return [{"dataset": {"uuid": dataset_id, "name": super_manifest.get("name")}, "pieces": pieces}]


def to_legacy_repair_manifest(manifest_json: object, repair_source_url: str) -> list[dict]:
    if isinstance(manifest_json, dict) and "@spec" in manifest_json:
        manifest = _super_manifest_to_manifest(manifest_json)
    elif isinstance(manifest_json, list) and manifest_json and isinstance(manifest_json[0], dict):
        manifest = manifest_json  # already in this CLI's format
    else:
        raise click.ClickException("Unsupported manifest format: expected this CLI's manifest or a data-prep-standard super-manifest")

    manifest[0][REPAIR_SOURCE_KEY] = repair_source_url.rstrip("/")
    return manifest
