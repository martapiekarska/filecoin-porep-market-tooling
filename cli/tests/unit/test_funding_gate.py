import importlib
from decimal import Decimal
from types import SimpleNamespace

import click
import pytest

from cli.commands.repair_funding import FundingHistoryUnavailable, RepairFunding
from cli.commands.repair_utils import RetrievalQuote, SourceUnavailable

od = importlib.import_module("cli.commands.sp.onboard_data")

USDFC = 10 ** 18
PIECES = [{"pieceCid": "bagaA"}, {"pieceCid": "bagaB"}]
DEAL = SimpleNamespace(deal=SimpleNamespace(deal_id=9, client_address="0xClient", proposed_at_epoch=100))


@pytest.fixture
def gate(monkeypatch):
    def setup(quote: RetrievalQuote | Exception, funding: RepairFunding | Exception):
        calls = SimpleNamespace(quoted=[], funding=[])

        def fake_quote(base_url, piece_cids):
            calls.quoted.append((base_url, piece_cids))
            if isinstance(quote, Exception):
                raise quote
            return quote

        def fake_funding(token, client, payee, since_block):
            calls.funding.append((token, client, payee, since_block))
            if isinstance(funding, Exception):
                raise funding
            return funding

        token = SimpleNamespace(address=lambda: "0xUSDFC", decimals=lambda: 18, symbol=lambda: "USDFC")
        monkeypatch.setattr(od, "repair_payment_token", lambda deal: "0xUSDFC")
        monkeypatch.setattr(od, "ERC20Contract", lambda address: token)
        monkeypatch.setattr(od, "resolve_repair_payee", lambda deal: "0xPayee")
        monkeypatch.setattr(od, "quote_retrieval", fake_quote)
        monkeypatch.setattr(od, "get_repair_funding", fake_funding)
        return calls

    return setup


def run(allow_unfunded_retrieval=False):
    od._ensure_repair_funded(DEAL, PIECES, "https://healthy.example", allow_unfunded_retrieval)


PAID = RetrievalQuote(total=Decimal("1.5"), paid_pieces=2, free_pieces=0)


def test_covered_quote_starts_the_download(gate):
    calls = gate(PAID, RepairFunding(deposited=2 * USDFC, spent=USDFC // 2))
    run()
    assert calls.quoted == [("https://healthy.example", ["bagaA", "bagaB"])]
    assert calls.funding == [("0xUSDFC", "0xClient", "0xPayee", 100)]


def test_short_funding_waits_for_the_client(gate):
    gate(PAID, RepairFunding(deposited=USDFC, spent=0))
    with pytest.raises(click.ClickException, match=r"Waiting for client funding: quote 1\.5 USDFC, available 1 USDFC, short 0\.5 USDFC") as e:
        run()
    assert "client pay-repair-retrieval 9" in e.value.message


def test_retry_after_partial_spend_needs_only_the_remaining_quote(gate):
    # first run paid for one piece and failed; the retry quotes only the piece left, against what is left of the deposit
    gate(RetrievalQuote(total=Decimal("0.75"), paid_pieces=1, free_pieces=0), RepairFunding(deposited=15 * USDFC // 10, spent=75 * USDFC // 100))
    run()


def test_spending_beyond_the_deposits_counts_as_nothing_available(gate):
    gate(PAID, RepairFunding(deposited=USDFC, spent=3 * USDFC))
    with pytest.raises(click.ClickException, match=r"available 0 USDFC, short 1\.5 USDFC"):
        run()


def test_short_funding_can_be_overridden(gate):
    gate(PAID, RepairFunding(deposited=0, spent=0))
    run(allow_unfunded_retrieval=True)


def test_unverifiable_funding_fails_closed(gate):
    gate(PAID, FundingHistoryUnavailable("lookback limit"))
    with pytest.raises(click.ClickException, match="Could not check the client's repair funding.*lookback limit"):
        run()


def test_unverifiable_funding_can_be_overridden(gate):
    gate(PAID, FundingHistoryUnavailable("lookback limit"))
    run(allow_unfunded_retrieval=True)


def test_free_quote_needs_no_funding(gate):
    calls = gate(RetrievalQuote(total=Decimal(0), paid_pieces=0, free_pieces=2), FundingHistoryUnavailable("not called"))
    run()
    assert not calls.funding


def test_unavailable_source_stops_before_any_payment(gate):
    calls = gate(SourceUnavailable("dataset incomplete"), RepairFunding(deposited=0, spent=0))
    with pytest.raises(click.ClickException, match="cannot serve the data: dataset incomplete"):
        run()
    assert not calls.funding


def test_gate_runs_before_retrieval_client(monkeypatch):
    order = []
    monkeypatch.setattr(od, "get_retrieval_client_path", lambda: "retrieval-client")
    monkeypatch.setattr(od, "_ensure_payee_key", lambda deal, key_file: order.append("key"))
    monkeypatch.setattr(od, "_ensure_repair_funded", lambda deal, pieces, host, allow: order.append(("gate", allow)) or (_ for _ in ()).throw(click.ClickException("short")))
    monkeypatch.setattr(od.subprocess, "run", lambda *args, **kwargs: order.append("fetch"))

    with click.Context(od.onboard_data) as ctx, pytest.raises(click.ClickException):
        od._download_with_lpr(ctx, DEAL, PIECES, "https://healthy.example", None, True, None, None, True)
    assert order == ["key", ("gate", True)]
