from decimal import Decimal

import click
import pytest

from cli import utils
from cli.commands import utils as commands_utils

SECTOR = 32 * 2 ** 30


@pytest.mark.parametrize("amount, decimals, expected", [
    ("1.1", 18, 1_100_000_000_000_000_000),  # binary float maths was 128 base units off here
    ("2.3", 18, 2_300_000_000_000_000_000),  # ... and 256 off here
    ("0.000000000000000001", 18, 1),
    ("123456789012345678901234567890.123456789012345678", 18, 123456789012345678901234567890123456789012345678),
    ("1.5", 6, 1_500_000),
    ("7", 0, 7),
    (Decimal("0.07"), 6, 70_000),
    (5, 18, 5 * 10 ** 18),
    (0.1, 18, 10 ** 17),  # a float is taken as the decimal it was written as
])
def test_to_wei_is_exact(amount, decimals, expected):
    assert utils.to_wei(amount, decimals) == expected


def test_to_wei_refuses_more_decimals_than_the_token_has():
    with pytest.raises(click.ClickException, match="more than 6 decimal places"):
        utils.to_wei("0.0000001", 6)


@pytest.mark.parametrize("wei, decimals, expected", [
    (269_780_000_000_000_000_000, 18, "269.780000000000000000"),  # was printed as 269.779999999999972715
    (1, 18, "0.000000000000000001"),
    (2 ** 256 - 1, 18, "115792089237316195423570985008687907853269984665640564039457.584007913129639935"),
    (0, 6, "0.000000"),
])
def test_str_from_wei_is_exact(wei, decimals, expected):
    assert utils.str_from_wei(wei, decimals) == expected
    assert utils.to_wei(utils.str_from_wei(wei, decimals), decimals) == wei


@pytest.mark.parametrize("text, expected", [("1.1", Decimal("1.1")), (" 0.5 ", Decimal("0.5")), ("1e-3", Decimal("0.001")), ("10", Decimal(10))])
def test_decimal_amount_parses_the_typed_text(text, expected):
    assert utils.DecimalAmount(min_open=True).convert(text, None, None) == expected


@pytest.mark.parametrize("text", ["abc", "", "NaN", "Infinity", "-1", "0"])
def test_decimal_amount_rejects_invalid_or_non_positive(text):
    with pytest.raises(click.BadParameter):
        utils.DecimalAmount(min_open=True).convert(text, None, None)


def test_decimal_amount_closed_range_allows_zero():
    assert utils.DecimalAmount().convert("0", None, None) == 0


def test_price_per_tib_to_per_sector_is_exact():
    # 32 sectors per TiB: 1.6 tokens/TiB -> 0.05 tokens per sector
    assert utils.price_per_TiB_tokens_to_per_sector_wei(Decimal("1.6"), 18, SECTOR) == 5 * 10 ** 16


def test_price_per_tib_that_does_not_split_into_sectors_is_refused():
    with pytest.raises(click.ClickException, match="does not split exactly"):
        utils.price_per_TiB_tokens_to_per_sector_wei(Decimal("0.000001"), 6, SECTOR)


def test_deposit_amount_uses_integer_maths():
    price = 31_250_000_000_000_001  # per sector per month; a float product would lose the trailing 1
    assert commands_utils.calculate_deposit_amount(3 * SECTOR, price, SECTOR, 2) == 3 * price * 2


def test_deposit_amount_bills_whole_32_gib_units():
    # mainnet deal 2: 853.001 units of data, billed by the contract as 854
    size = 853 * SECTOR + 34_359_738
    assert commands_utils.billed_32_gib_units(size, SECTOR) == 854
    assert commands_utils.calculate_deposit_amount(size, 125 * 10 ** 15, SECTOR) == 854 * 125 * 10 ** 15


def _deal(rate: int, billed: int, price: int, size: int):
    from types import SimpleNamespace
    return SimpleNamespace(payment=SimpleNamespace(rail_max_rate_per_epoch=rate, billed_32_gib_units=billed, price_per_32_gib_per_month=price),
                           terms=SimpleNamespace(requested_size_bytes=size))


def test_deal_deposit_matches_what_the_rail_streams(monkeypatch):
    monkeypatch.setattr(commands_utils, "PoRepMarket", lambda: type("M", (), {"get_epochs_in_month": lambda self: 86_400})())
    # mainnet deal 2: the contract rounds the rate per epoch up, so the rail streams slightly more than units * price
    deal = _deal(rate=1_235_532_407_407_408, billed=854, price=125 * 10 ** 15, size=853 * SECTOR + 1)
    assert commands_utils.deal_deposit_amount(deal, 2) == 1_235_532_407_407_408 * 86_400 * 2
    assert commands_utils.deal_deposit_amount(deal) - 854 * 125 * 10 ** 15 == 51_200


def test_deal_deposit_falls_back_to_billed_units_before_a_rate_is_set(monkeypatch):
    monkeypatch.setattr(commands_utils, "PoRepMarket", lambda: type("M", (), {"get_sector_size_bytes": lambda self: SECTOR})())
    assert commands_utils.deal_deposit_amount(_deal(rate=0, billed=0, price=7, size=2 * SECTOR + 1), 3) == 3 * 7 * 3
