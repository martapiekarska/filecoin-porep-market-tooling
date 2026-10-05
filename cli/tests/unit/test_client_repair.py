import importlib
from types import SimpleNamespace

import click
import pytest

from cli.commands.client import _repair
from cli.services.contracts.porep_market import PoRepMarketDealState

repair_module = importlib.import_module("cli.commands.client.repair")

CLIENT, HASH = "0xClient", b"\x01" * 32
OLD = SimpleNamespace(deal=SimpleNamespace(deal_id=10, provider_id="f01", proposed_at_epoch=1000, client_address=CLIENT),
                      data=SimpleNamespace(manifest_hash=HASH, manifest_location="https://m.example/manifest.json"))


def deal(deal_id, state, provider_id="f02", proposed_at_epoch=2000, manifest_hash=HASH):
    return SimpleNamespace(deal=SimpleNamespace(deal_id=deal_id, state=PoRepMarketDealState[state], provider_id=provider_id,
                                                proposed_at_epoch=proposed_at_epoch, client_address=CLIENT),
                           data=SimpleNamespace(manifest_hash=manifest_hash))


@pytest.fixture
def chain(monkeypatch):
    def setup(*views):
        by_id = {view.deal.deal_id: view for view in views}
        monkeypatch.setattr(repair_module, "client_address", lambda: CLIENT)
        monkeypatch.setattr(repair_module.commands_utils, "get_client_deals", lambda client: [view.deal for view in views])
        monkeypatch.setattr(repair_module, "PoRepMarketViewHelper", lambda: SimpleNamespace(get_deal_view=lambda deal_id: by_id[deal_id]))
        return by_id
    return setup


def test_resumes_the_latest_pending_repair_deal(chain):
    chain(deal(11, "PROPOSED"), deal(12, "ACCEPTED"), deal(13, "REJECTED"))
    assert repair_module._find_repair_deal(OLD, False).deal.deal_id == 12


@pytest.mark.parametrize("other", [
    deal(11, "ACCEPTED", provider_id="f01"),          # the repaired deal's own SP
    deal(11, "ACCEPTED", proposed_at_epoch=900),      # proposed before the repaired deal
    deal(11, "ACCEPTED", manifest_hash=b"\x02" * 32),  # another dataset
    deal(11, "REJECTED"),
])
def test_ignores_deals_that_are_not_this_repair(chain, other):
    chain(other)
    assert repair_module._find_repair_deal(OLD, False) is None


def test_active_later_deal_means_the_repair_is_done(chain):
    chain(deal(11, "ACTIVE"))
    with pytest.raises(click.ClickException, match="repair looks done"):
        repair_module._find_repair_deal(OLD, False)
    assert repair_module._find_repair_deal(OLD, True) is None


def test_old_terms_convert_back_exactly(monkeypatch):
    monkeypatch.setattr(repair_module, "ERC20Contract", lambda address: SimpleNamespace(decimals=lambda: 18))
    monkeypatch.setattr(repair_module, "PoRepMarket", lambda: SimpleNamespace(get_sector_size_bytes=lambda: 32 * 2 ** 30))
    old = SimpleNamespace(deal=SimpleNamespace(deal_id=2), payment=SimpleNamespace(payment_token="0xUSDFC", price_per_32_gib_per_month=125 * 10 ** 15),
                          terms=SimpleNamespace(duration_epochs=518400))
    assert repair_module._old_price_per_tib(old) == 4.0
    assert repair_module._old_duration_months(old) == 6

    old.terms.duration_epochs += 1
    with pytest.raises(click.UsageError, match="--duration-months"):
        repair_module._old_duration_months(old)


@pytest.fixture
def flow(monkeypatch, chain):
    def setup(new_state_after_wait: str):
        new = deal(11, "PROPOSED")
        chain(OLD, new)
        steps = []
        monkeypatch.setattr(repair_module.SelfUpdateService, "check_and_prompt", lambda manual: None)
        monkeypatch.setattr(repair_module._repair, "ensure_repairable", lambda view: None)
        monkeypatch.setattr(repair_module, "ensure_usdfc", lambda token, subject: None)
        monkeypatch.setattr(repair_module, "_find_repair_deal", lambda old, propose_new: new)
        monkeypatch.setattr(repair_module, "_wait_for_acceptance", lambda deal_id, minutes: deal(deal_id, new_state_after_wait))
        monkeypatch.setattr(repair_module._repair, "pay_repair_retrieval", lambda *args, **kwargs: steps.append(("pay", args[0], kwargs["covered_is_done"])))
        monkeypatch.setattr(repair_module.init_deal, "callback", lambda deal_id: steps.append(("init", deal_id)))
        monkeypatch.setattr(repair_module.make_allocations, "callback", lambda deal_id, **kwargs: steps.append(("allocate", deal_id)))
        OLD.payment = SimpleNamespace(payment_token="0xUSDFC")
        return steps
    return setup


def run_repair(**kwargs):
    with click.Context(repair_module.repair) as ctx:
        ctx.invoke(repair_module.repair, deal_id=10, **kwargs)


def test_accepted_repair_deal_is_funded_initialized_and_allocated(flow):
    steps = flow("ACCEPTED")
    run_repair()
    assert steps == [("pay", 11, True), ("init", 11), ("allocate", 11)]


def test_unaccepted_repair_deal_stops_without_paying(flow, capsys):
    steps = flow("PROPOSED")
    run_repair()
    assert steps == []
    assert "client repair 10" in capsys.readouterr().out


def test_rejected_repair_deal_asks_to_rerun(flow):
    steps = flow("REJECTED")
    with pytest.raises(click.ClickException, match="propose a new one"):
        run_repair()
    assert steps == []


def test_resumed_deposit_already_covered_is_not_an_error(monkeypatch):
    monkeypatch.setattr(_repair, "client_address", lambda: CLIENT)
    monkeypatch.setattr(_repair, "get_repair_deposits", lambda token, client, payee, since: 5)
    assert _repair._check_previous_deposits("0xT", "0xP", 1, 5, 0, "USDFC", False, False, covered_is_done=True) == 0
    with pytest.raises(click.ClickException, match="not depositing again"):
        _repair._check_previous_deposits("0xT", "0xP", 1, 5, 0, "USDFC", False, False)
