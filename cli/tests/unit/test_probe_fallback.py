from decimal import Decimal
from types import SimpleNamespace

import click
import pytest

from cli.commands import repair_utils
from cli.commands.client import _repair
from cli.commands.repair_utils import PieceProbe, RetrievalQuote

BASE = "https://sp.example:443"
PIECES = [{"pieceCid": f"baga{i}", "fileSize": 100 + i} for i in range(3)]
EXACT = RetrievalQuote(total=Decimal("1.5"), paid_pieces=3, free_pieces=0)


@pytest.fixture
def source(monkeypatch):
    def setup(probes: dict[str, PieceProbe] | None = None, retrieval_client: str | None = None):
        calls = SimpleNamespace(probed=[], quoted=[])

        def fake_probe(base_url, cid):
            calls.probed.append(cid)
            return (probes or {}).get(cid, PieceProbe(status="free"))

        def fake_quote(base_url, cids):
            calls.quoted.append(cids)
            return EXACT

        monkeypatch.setattr(repair_utils.commands_utils, "validate_and_parse_url", lambda url: None)
        monkeypatch.setattr(repair_utils, "find_retrieval_client", lambda: retrieval_client)
        monkeypatch.setattr(repair_utils, "probe_piece", fake_probe)
        monkeypatch.setattr(repair_utils, "quote_retrieval", fake_quote)
        return calls

    return setup


def test_free_source_without_retrieval_client_probes_every_piece(source):
    calls = source({"baga1": PieceProbe(status="free", size_bytes=101)})
    found, reason = repair_utils.quote_source(BASE, PIECES, probe_fallback=True)

    assert reason == "ok" and found.is_free()
    assert (found.quote.total, found.quote.free_pieces) == (0, 3)
    assert calls.probed == ["baga0", "baga1", "baga2"] and not calls.quoted


def test_paid_piece_without_retrieval_client_asks_to_install_it(source):
    calls = source({"baga1": PieceProbe(status="paid")})
    with pytest.raises(click.ClickException, match=r"charges for piece baga1 \(HTTP 402\).*needs retrieval-client"):
        repair_utils.quote_source(BASE, PIECES, probe_fallback=True)
    assert calls.probed == ["baga0", "baga1"]


@pytest.mark.parametrize("probe, reason", [
    (PieceProbe(status="unavailable", detail="HTTP 404"), "baga2: unavailable (HTTP 404)"),
    (PieceProbe(status="private", detail="403 Forbidden"), "baga2: private (403 Forbidden)"),
    (PieceProbe(status="free", size_bytes=7), "baga2: size 7 != manifest fileSize 102"),
])
def test_source_missing_a_piece_is_refused(source, probe, reason):
    source({"baga2": probe})
    found, why = repair_utils.quote_source(BASE, PIECES, probe_fallback=True)
    assert found is None and reason in why


def test_retrieval_client_is_used_whenever_installed(source):
    calls = source(retrieval_client="/usr/local/bin/retrieval-client")
    found, _ = repair_utils.quote_source(BASE, PIECES, probe_fallback=True)
    assert found.quote == EXACT and calls.quoted and not calls.probed


def test_without_fallback_retrieval_client_stays_required(source):
    calls = source()
    repair_utils.quote_source(BASE, PIECES)
    assert calls.quoted and not calls.probed  # quote_retrieval itself reports the missing retrieval-client


def test_given_source_url_passes_the_fallback_through(source):
    source()
    found = repair_utils.find_healthy_source(b"", PIECES, set(), f"{BASE}/", probe_fallback=True)
    assert found.base_url == BASE and found.is_free()


def test_missing_retrieval_client_is_detected_quietly(monkeypatch, tmp_path):
    monkeypatch.setenv("RETRIEVAL_CLIENT_PATH", str(tmp_path / "nope"))
    assert repair_utils.find_retrieval_client() is None
    with pytest.raises(click.ClickException, match="not found"):
        repair_utils.get_retrieval_client_path()


@pytest.mark.parametrize("embedded, fallback", [("https://legacy.example", True), (None, False)])
def test_payment_step_uses_the_fallback_only_for_legacy_sources(monkeypatch, embedded, fallback):
    from cli.services.contracts.porep_market import PoRepMarketDealState

    deal = SimpleNamespace(deal=SimpleNamespace(deal_id=5, client_address="0xC", state=PoRepMarketDealState.ACCEPTED, provider_id="f02"),
                           data=SimpleNamespace(manifest_location="https://m.example/m.json"))
    seen = {}

    def fake_find(deal_view, pieces, repair_of, source_url, probe_fallback=False):
        seen.update(source_url=source_url, probe_fallback=probe_fallback)
        return repair_utils.RetrievalSource(base_url=source_url or BASE, quote=RetrievalQuote(total=Decimal(0), paid_pieces=0, free_pieces=1))

    monkeypatch.setattr(_repair, "Web3Service", lambda: SimpleNamespace(wait_for_pending_transactions=lambda address: None))
    monkeypatch.setattr(_repair, "PoRepMarketViewHelper", lambda: SimpleNamespace(get_deal_view=lambda deal_id: deal))
    monkeypatch.setattr(_repair, "client_address", lambda: "0xC")
    monkeypatch.setattr(_repair, "repair_payment_token", lambda view: "0xUSDFC")
    monkeypatch.setattr(_repair, "ERC20Contract", lambda address: SimpleNamespace())
    monkeypatch.setattr(_repair.commands_utils, "fetch_manifest", lambda *args, **kwargs: ([{"pieces": [{"pieceCid": "baga0"}]}], b""))
    monkeypatch.setattr(_repair, "get_manifest_repair_source", lambda manifest: embedded)
    monkeypatch.setattr(_repair, "find_repair_source", fake_find)

    _repair.pay_repair_retrieval(5)
    assert seen == {"source_url": embedded, "probe_fallback": fallback}
