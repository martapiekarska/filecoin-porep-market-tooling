from decimal import Decimal

import click
import pytest

from cli.commands.repair_utils import DecimalAmount


@pytest.mark.parametrize("text, expected", [("0.01", Decimal("0.01")), (" 0.5 ", Decimal("0.5")), ("1e-3", Decimal("0.001"))])
def test_repair_price_is_parsed_exactly_from_the_typed_text(text, expected):
    assert DecimalAmount(min_open=True).convert(text, None, None) == expected


@pytest.mark.parametrize("text", ["abc", "", "NaN", "Infinity", "-1", "0"])
def test_repair_price_rejects_invalid_or_non_positive(text):
    with pytest.raises(click.BadParameter):
        DecimalAmount(min_open=True).convert(text, None, None)
