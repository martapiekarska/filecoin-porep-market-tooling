import dataclasses
import enum
import json
import os
import sys
from collections.abc import Callable
from decimal import Decimal, InvalidOperation, localcontext
from typing import TypeVar

import click
from dotenv import load_dotenv

load_dotenv(dotenv_path=None)

MAX_UINT256 = 2 ** 256 - 1
DATACAP_DECIMALS = 18
FIL_TOKEN_DECIMALS = 18

T = TypeVar("T")


def get_env_required(name, default: T | None = None, required_type: Callable[[str], T] = str) -> T:
    return get_env(name, required=True, default=default, required_type=required_type)


def get_env(name, required=False, default: T | None = None, required_type: Callable[[str], T] = str) -> T | None:
    value = os.getenv(name)

    def is_empty(v):
        return v is None or v.strip() == ""

    if is_empty(value) and default is not None:
        return default

    if is_empty(value):
        if required:
            raise RuntimeError(f"Environment variable {name} is not set, see .env file")

        return None

    # noinspection PyTypeChecker
    return required_type(value)


def string_to_bool(value: str | None) -> bool | None:
    if value is None:
        return None

    value = value.strip().lower()

    if value in ["true", "1", "yes", "y"]:
        return True
    elif value in ["false", "0", "no", "n"]:
        return False
    else:
        raise ValueError(f"Unknown boolean value: {value}")


_confirm_yes_for_all_sessions: set[str] = set()


def confirm(text: str,
            default: bool | None = False,
            abort: bool = False,
            session_id: str | None = None) -> bool:
    #
    answer = "yes" if session_id and session_id in _confirm_yes_for_all_sessions else None
    default_answer = "yes" if default else "no" if default is False else None
    yes_for_all_answers = ["all"] if session_id else []
    yes_answers = ["yes"]
    no_answers = ["no"]

    answer = confirm_str(text=text,
                         default=default_answer,
                         valid_answers=yes_answers + no_answers + yes_for_all_answers,
                         answer=answer).strip().lower()

    if answer in no_answers:
        if abort:
            raise click.Abort()
        else:
            return False
    #
    elif answer in yes_for_all_answers and session_id:
        _confirm_yes_for_all_sessions.add(session_id)
        return True
    elif answer in yes_answers:
        return True
    else:
        assert False  # should not happen


# if answer is set, print the prompt and return the answer immediately without asking the user
# this function supports only case insensitive mode
def confirm_str(text: str,
                default: str | None = None,
                valid_answers: list[str] | None = None,
                prompt_suffix: str = ": ",
                show_choices: bool = True,
                answer: str | None = None,
                allow_short_answer: bool = True) -> str:
    #
    valid_answers = [_answer.strip().lower() for _answer in valid_answers] if valid_answers else []
    default = default.strip().lower() if default else None

    if default is not None and valid_answers and default not in valid_answers:
        valid_answers = [default] + valid_answers

    if allow_short_answer:
        # pylint: disable=unsubscriptable-object
        valid_answers_short = {answer[0]: answer for answer in valid_answers}

        if len(valid_answers_short) != len(valid_answers):
            raise RuntimeError("Short answers are not unique")
    else:
        valid_answers_short = {}

    valid_answers_labels = [answer.capitalize() if answer == default else answer for answer in valid_answers]
    valid_answers_labels = f" [{'/'.join(valid_answers_labels)}]" if valid_answers_labels and show_choices else ""
    text = f"{text}{valid_answers_labels}{prompt_suffix}"

    if answer is not None:
        click.echo(text + answer)
        return answer.strip().lower()

    while True:
        answer = click.prompt(text=text,
                              prompt_suffix="",
                              default=default,
                              show_default=False).strip().lower()

        if not valid_answers or answer in valid_answers:
            return answer
        if answer in valid_answers_short:
            return valid_answers_short[answer]
        else:
            continue

    assert False  # should not happen


# equivalent to "press enter to continue"
def confirm_ok(prompt: str):
    _ = confirm_str(f"{prompt} [Press enter to continue]", default="OK", prompt_suffix=" ")


def json_dataclass(eq=True, init=True, **d_kwargs):
    def wrapper(cls):
        cls = dataclasses.dataclass(**d_kwargs, eq=eq, init=init)(cls)

        def __str__(self):
            # noinspection PyTypeChecker
            return json_pretty(dataclasses.asdict(self))

        cls.__str__ = __str__
        return cls

    return wrapper


def json_pretty(json_data, sort_keys: bool = False):
    def _json_pretty(data):
        if issubclass(type(data), enum.Enum):
            return data.name
        if isinstance(data, (bytes, bytearray)):
            return "0x" + data.hex()
        if hasattr(data, "__json__") and callable(data.__json__):
            return data.__json__()
        if hasattr(data, "__dict__") and data.__dict__:
            return _json_pretty(data.__dict__)
        if isinstance(data, list):
            return [_json_pretty(item) for item in data]
        if isinstance(data, dict) and data:
            return {key: _json_pretty(value) for key, value in data.items()}
        # pylint: disable=unidiomatic-typecheck
        if not isinstance(data, bool) and type(data) is not int and isinstance(data, int):
            return str(data)

        return data

    return json.dumps(_json_pretty(json_data), indent=4, sort_keys=sort_keys, default=str)


# Token amounts are Decimals parsed from the user's text and integers in base units; never binary floats, which can't
# represent most decimal amounts exactly (e.g. 1.1 * 10**18 as a float is 128 base units off).
AMOUNT_PRECISION = 100  # significant digits for amount arithmetic; uint256 has at most 78


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


def to_decimal(amount: Decimal | str | float) -> Decimal:
    # a float (e.g. from a database driver) is converted from its shortest repr, i.e. the decimal it was written as
    return amount if isinstance(amount, Decimal) else Decimal(str(amount))


# converts 1100000000000000000 wei -> Decimal("1.1") ETH, exactly
def from_wei(amount: int, decimals: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = AMOUNT_PRECISION
        return Decimal(int(amount)).scaleb(-decimals)


def str_from_wei(amount: int, decimals: int) -> str:
    return f"{from_wei(amount, decimals):.{decimals}f}"


# converts 1.1 ETH -> 1100000000000000000 wei, exactly; refuses amounts with more decimal places than the token has
def to_wei(amount: Decimal | str | float, decimals: int) -> int:
    with localcontext() as ctx:
        ctx.prec = AMOUNT_PRECISION
        result = to_decimal(amount).scaleb(decimals)

        if result != result.to_integral_value():
            raise click.ClickException(f"Amount {amount} has more than {decimals} decimal places")

        return int(result)


# returns minimal size if size is None
def uint_to_bytes(x: int, size: int | None = 32) -> bytes:
    if x < 0:
        raise ValueError("Cannot convert negative integer to bytes")

    if size is None:
        if x == 0:
            return b"\x00"

        size = (x.bit_length() + 7) // 8

    if not size or size < 0:
        raise ValueError(f"Invalid size: {size}")

    return x.to_bytes(size, "big")


def private_str_to_log_str(private_str) -> str:
    if not private_str:
        return ""

    if isinstance(private_str, bytes):
        _private_str = "0x" + private_str.hex()
    elif isinstance(private_str, int):
        _private_str = hex(private_str)
    else:
        _private_str = str(private_str)

    hex_padding = 2 if _private_str.startswith("0x") else 0

    if len(_private_str) > 65:
        return f"{_private_str[:4 + hex_padding]}...{_private_str[-4:]}"

    if len(_private_str) > 40:
        return f"{_private_str[:2 + hex_padding]}...{_private_str[-2:]}"

    if len(_private_str) > 20:
        return f"{_private_str[:1 + hex_padding]}...{_private_str[-1:]}"

    if len(_private_str) > 5:
        return "*" * len(_private_str)

    return "*" * 5


# for display only; do size arithmetic in integers
def bytes_to_sectors(bytes_size: int, sector_size_bytes: int) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = AMOUNT_PRECISION
        return (Decimal(bytes_size) / Decimal(sector_size_bytes)).normalize()


def months_to_epochs(months: int, epochs_in_month: int) -> int:
    return months * epochs_in_month


# noinspection PyPep8Naming,PyShadowingNames
# pylint: disable=invalid-name
def Mbps_to_Bps(Mbps: int) -> int:
    MBPS_TO_BYTES_PER_SECOND = 125_000  # 1 Mbps = 10^6 bits/s / 8 = 125 000 bytes/s
    return Mbps * MBPS_TO_BYTES_PER_SECOND


# noinspection PyPep8Naming,PyShadowingNames
# pylint: disable=invalid-name
def price_per_TiB_tokens_to_per_sector_wei(
        price_per_TiB_tokens: Decimal,
        payment_token_decimals: int,
        sector_size_bytes: int,
) -> int:
    TIB_BYTES = 1024 ** 4  # 1 TiB in bytes

    if sector_size_bytes <= 0:
        raise ValueError(f"Invalid sector size: {sector_size_bytes}")

    sectors_per_TiB, size_remainder = divmod(TIB_BYTES, sector_size_bytes)

    if size_remainder != 0:
        raise ValueError(f"Sector size {sector_size_bytes} does not divide 1 TiB exactly")

    price_per_TiB_wei = to_wei(price_per_TiB_tokens, payment_token_decimals)
    price_per_sector_wei, price_remainder = divmod(price_per_TiB_wei, sectors_per_TiB)

    if price_remainder != 0:
        raise click.ClickException(f"Price {price_per_TiB_tokens} per TiB does not split exactly into {sectors_per_TiB} sectors "
                                   f"in base units; use a price whose base-unit value is a multiple of {sectors_per_TiB}")

    return price_per_sector_wei


def _show(self, file=None):
    if file is None:
        file = sys.stderr

    click.secho(f"\nError: {self.format_message()}", fg="red", err=True, file=file)


click.ClickException.show = _show
