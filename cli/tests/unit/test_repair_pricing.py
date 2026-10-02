from decimal import Decimal

import pytest

from cli.commands import repair_utils
from cli.commands.client import _repair

GIB = 2 ** 30


@pytest.mark.parametrize("file_size, padded", [
    (13, 128), (127, 128), (128, 256),  # 128-byte minimum piece, FR32 expansion of 127 bytes per 128
    (18_801_996, 33_554_432), (32_849_050_527, 34_359_738_368),  # RarePlanes dag and data pieces, checked against on-chain claims
    (34_091_302_912, 34_359_738_368), (34_091_302_913, 68_719_476_736),  # exactly 32 GiB of FR32 capacity, and one byte more
])
def test_padded_piece_size(file_size, padded):
    assert repair_utils._padded_piece_size(file_size) == padded


def test_estimate_rounds_each_piece_up_to_whole_gib():
    pieces = [{"pieceCid": "a", "fileSize": GIB, "pieceSize": 32 * GIB}, {"pieceCid": "b", "fileSize": GIB + 1, "pieceSize": 32 * GIB},
              {"pieceCid": "c", "fileSize": 13, "pieceSize": 128}]
    assert _repair.estimate_retrieval_cost(pieces, 10 ** 16) == (1 + 2 + 1) * 10 ** 16


def test_estimate_warns_when_falling_back_to_piece_size(capsys):
    pieces = [{"pieceCid": "nofilesize", "fileSize": 0, "pieceSize": 32 * GIB}]
    assert _repair.estimate_retrieval_cost(pieces, 1) == 32
    assert "nofilesize" in capsys.readouterr().out


@pytest.mark.parametrize("price, decimals, expected", [
    (Decimal("0.01"), 18, 10 ** 16),
    (Decimal("0.1") / 3, 18, 33_333_333_333_333_334),  # inexact quote-derived price: rounded up, flow continues
    (Decimal("0.0000001"), 6, 1),
])
def test_price_to_wei_rounds_up(price, decimals, expected):
    assert _repair.price_to_wei(price, decimals) == expected


def test_price_per_gib_derivation_keeps_full_precision(monkeypatch):
    # an exact per-GiB price with 40 significant digits; Decimal's default 28-digit context would round it
    per_gib = Decimal("1234567890123456789012345678.901234567891")
    monkeypatch.setattr(repair_utils, "probe_piece",
                        lambda base_url, cid: repair_utils.PieceProbe(status="paid", size_bytes=3 * GIB, price=Decimal("3703703670370370367037037036.703703703673")))  # per_gib * 3, exactly
    source, _ = repair_utils.probe_source("https://sp.example", [{"pieceCid": "a", "fileSize": 3 * GIB}])
    assert source.price_per_gib == per_gib


def test_inconsistent_quotes_use_the_highest_price(monkeypatch):
    prices = iter([Decimal("0.03"), Decimal("0.06")])
    monkeypatch.setattr(repair_utils, "probe_piece",
                        lambda base_url, cid: repair_utils.PieceProbe(status="paid", size_bytes=3 * GIB, price=next(prices)))
    source, _ = repair_utils.probe_source("https://sp.example", [{"pieceCid": "a", "fileSize": 3 * GIB}, {"pieceCid": "b", "fileSize": 3 * GIB}])
    assert source.price_per_gib == Decimal("0.02")


class _Response:
    def __init__(self, status_code, headers):
        self.status_code, self.headers = status_code, headers

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _challenge(request: object) -> str:
    import base64
    import json
    encoded = base64.urlsafe_b64encode(json.dumps(request).encode()).rstrip(b"=").decode()
    return f'Payment id="x", realm="piece:h", method="filecoinpay", intent="charge", request="{encoded}"'


@pytest.mark.parametrize("www_authenticate, expected", [
    (_challenge({"price_usdfc": "0.31", "payee_0x": "0xabc"}), "paid"),
    (_challenge({"price_usdfc": "not-a-number"}), "unavailable"),
    (_challenge({"price_usdfc": "NaN"}), "unavailable"),
    (_challenge({"price_usdfc": "-1"}), "unavailable"),
    (_challenge(["not", "an", "object"]), "unavailable"),
    (_challenge({}), "unavailable"),
    ('Payment request="!!!not-base64!!!"', "unavailable"),
    ("Bearer something-else", "unavailable"),
])
def test_malformed_quotes_make_the_source_unavailable(monkeypatch, www_authenticate, expected):
    monkeypatch.setattr(repair_utils.commands_utils, "validate_and_parse_url", lambda url: None)
    monkeypatch.setattr(repair_utils.requests, "head", lambda *a, **k: _Response(200, {"Content-Length": str(31 * GIB)}))
    monkeypatch.setattr(repair_utils.requests, "get", lambda *a, **k: _Response(402, {"WWW-Authenticate": www_authenticate}))
    assert repair_utils.probe_piece("https://sp.example", "baga").status == expected
