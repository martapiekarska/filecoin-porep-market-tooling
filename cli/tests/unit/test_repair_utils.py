import base64
import json
from decimal import Decimal
from types import SimpleNamespace

import click
import pytest

from cli.commands import repair_utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market import PoRepMarketDealState, PoRepMarketDealType

GIB = 2 ** 30


def _varint(n: int) -> bytes:
    out = b""
    while True:
        byte, n = n & 0x7F, n >> 7
        out += bytes([byte | (0x80 if n else 0)])
        if not n:
            return out


def _multiaddr(*parts) -> bytes:  # (code, value bytes or None, length-prefixed?)
    return b"".join(_varint(code) + ((_varint(len(value)) if prefixed else b"") + value if value is not None else b"")
                    for code, value, prefixed in parts)


@pytest.mark.parametrize("raw, text", [
    (_multiaddr((53, b"mkt.lotus.dedyn.io", True), (6, (443).to_bytes(2, "big"), False), (478, None, False)), "/dns/mkt.lotus.dedyn.io/tcp/443/wss"),
    (_multiaddr((4, bytes([1, 2, 3, 4]), False), (6, (8787).to_bytes(2, "big"), False), (480, None, False)), "/ip4/1.2.3.4/tcp/8787/http"),
    (_multiaddr((4, bytes([1, 2, 3, 4]), False), (6, (24001).to_bytes(2, "big"), False)), "/ip4/1.2.3.4/tcp/24001"),
    (_multiaddr((4, bytes([1, 2, 3, 4]), False), (273, b"\x00\x01", False)), None),  # udp: unsupported protocol
    (b"\x04\x01", None),  # truncated
])
def test_multiaddr_to_string(raw, text):
    assert repair_utils.multiaddr_to_string(raw) == text


@pytest.mark.parametrize("addr, base", [
    ("/dns/mkt.lotus.dedyn.io/tcp/443/wss", "https://mkt.lotus.dedyn.io:443"),  # Curio market convention
    ("/ip4/1.2.3.4/tcp/8787/http", "http://1.2.3.4:8787"),
    ("/ip6/2001:db8::1/tcp/443/https", "https://[2001:db8::1]:443"),
    ("/dns4/sp.example.com/tcp/80/ws", "http://sp.example.com:80"),
    ("/ip4/1.2.3.4/tcp/443/tls/http", "https://1.2.3.4:443"),
    ("/ip4/1.2.3.4/tcp/24001", None),
    ("/ip4/1.2.3.4/udp/443/quic-v1", None),
])
def test_http_base_from_multiaddr(addr, base):
    assert repair_utils.http_base_from_multiaddr(addr) == base


def test_discover_prefers_cid_contact_http_addresses(monkeypatch):
    miner_info = {"PeerId": "12D3Koo", "Multiaddrs": [base64.b64encode(_multiaddr((53, b"chain.example", True), (6, (443).to_bytes(2, "big"), False), (478, None, False))).decode()]}
    monkeypatch.setattr(repair_utils, "Web3Service", lambda: SimpleNamespace(w3=lambda: SimpleNamespace(provider=SimpleNamespace(make_request=lambda m, p: {"result": miner_info}))))
    monkeypatch.setattr(repair_utils.requests, "get", lambda url, timeout: SimpleNamespace(ok=True, text=json.dumps({"Addrs": ["/dns/ipni.example/tcp/8787/http", "/ip4/1.1.1.1/tcp/1"]})))
    assert repair_utils.discover_provider_http_bases(1234) == ["http://ipni.example:8787"]


def test_discover_falls_back_to_on_chain_multiaddrs(monkeypatch):
    miner_info = {"PeerId": "12D3Koo", "Multiaddrs": [base64.b64encode(_multiaddr((53, b"chain.example", True), (6, (443).to_bytes(2, "big"), False), (478, None, False))).decode()]}
    monkeypatch.setattr(repair_utils, "Web3Service", lambda: SimpleNamespace(w3=lambda: SimpleNamespace(provider=SimpleNamespace(make_request=lambda m, p: {"result": miner_info}))))
    monkeypatch.setattr(repair_utils.requests, "get", lambda url, timeout: SimpleNamespace(ok=False, text=""))
    assert repair_utils.discover_provider_http_bases(1234) == ["https://chain.example:443"]


def _super_manifest(sizes: list[int]) -> dict:
    cids = [f"baga{i}" for i in range(len(sizes))]
    return {"@spec": "https://example/spec", "uuid": "dataset-uuid", "name": "Rare Planes",
            "pieces": [{"piece_cid": cid, "payload_cid": "bafy"} for cid in cids],
            "contents": [{"@type": "file", "name": f"{cid}.car", "byte_length": size, "piece_cid": cid} for cid, size in zip(cids, sizes)]}


def test_super_manifest_conversion_produces_a_valid_manifest():
    manifest = repair_utils.to_legacy_repair_manifest(_super_manifest([32_849_050_527, 18_801_996, 6_730_000_000]), "https://sp.example:8787/")
    pieces = manifest[0]["pieces"]

    assert manifest[0][repair_utils.REPAIR_SOURCE_KEY] == "https://sp.example:8787"
    assert [p["pieceType"] for p in pieces] == ["data", "dag", "data"]  # the smallest piece is the DAG piece
    assert [p["pieceSize"] for p in pieces] == [34_359_738_368, 33_554_432, 8_589_934_592]
    assert pieces[0]["storagePath"] == "baga0.car" and pieces[0]["fileSize"] == 32_849_050_527
    assert commands_utils._validate_manifest(manifest, quiet=True) == manifest


@pytest.mark.parametrize("super_manifest", [
    {**_super_manifest([10, 20]), "contents": []},  # no CAR entries
    _super_manifest([10]),  # no data piece besides the DAG piece
    {**_super_manifest([10, 20]), "contents": [{"name": "baga0.car", "byte_length": "10", "piece_cid": "baga0"}]},  # non-integer size
])
def test_unsupported_super_manifests_are_refused(super_manifest):
    with pytest.raises(click.ClickException):
        repair_utils.to_legacy_repair_manifest(super_manifest, "https://sp.example")


def test_cli_format_manifest_passes_through_with_the_repair_source(tmp_path):
    manifest = [{"pieces": [{"pieceCid": "a"}]}]
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert repair_utils.to_legacy_repair_manifest(repair_utils.load_manifest_json(str(path)), "https://sp.example")[0]["repairSource"] == "https://sp.example"


def _view(deal_id, provider, manifest_hash=b"h", state=PoRepMarketDealState.ACTIVE, deal_type=PoRepMarketDealType.PUBLIC):
    return SimpleNamespace(deal=SimpleNamespace(deal_id=deal_id, provider_id=provider, state=state, deal_type=deal_type),
                           data=SimpleNamespace(manifest_hash=manifest_hash))


def test_find_healthy_source_prefers_free_and_skips_unusable_deals(monkeypatch):
    views = [_view(1, 100),  # excluded provider (the SP being repaired)
             _view(2, 200),  # healthy, paid
             _view(3, 300, deal_type=PoRepMarketDealType.PRIVATE),  # LPR can't serve it to the new SP
             _view(4, 400, manifest_hash=b"other"),  # another dataset
             _view(5, 500, state=PoRepMarketDealState.FINALIZED),  # not active
             _view(6, 600),  # healthy, free
             _view(7, 700)]  # active but not serving
    prices = {"https://p200": Decimal("0.02"), "https://p600": Decimal(0)}
    probed = []

    def probe_source(base_url, pieces):
        probed.append(base_url)
        if base_url in prices:
            return repair_utils.RetrievalSource(base_url=base_url, price_per_gib=prices[base_url]), "ok"
        return None, "HTTP 500"

    monkeypatch.setattr(repair_utils, "PoRepMarketViewHelper", lambda: SimpleNamespace(get_deal_views=lambda: views))
    monkeypatch.setattr(repair_utils.commands_utils, "get_deal_claim_ids", lambda deal: [1])
    monkeypatch.setattr(repair_utils, "discover_provider_http_bases", lambda provider: [f"https://p{provider}"])
    monkeypatch.setattr(repair_utils, "probe_source", probe_source)

    source = repair_utils.find_healthy_source(b"h", [], exclude_provider_ids={100})

    assert (source.deal_id, source.provider_id, source.price_per_gib) == (6, 600, 0)
    assert probed == ["https://p200", "https://p600", "https://p700"]


def test_find_healthy_source_fails_when_nothing_serves(monkeypatch):
    monkeypatch.setattr(repair_utils, "PoRepMarketViewHelper", lambda: SimpleNamespace(get_deal_views=lambda: [_view(1, 100)]))
    monkeypatch.setattr(repair_utils.commands_utils, "get_deal_claim_ids", lambda deal: [])  # no claims on-chain
    with pytest.raises(click.ClickException, match="No healthy SP"):
        repair_utils.find_healthy_source(b"h", [], exclude_provider_ids=set())
