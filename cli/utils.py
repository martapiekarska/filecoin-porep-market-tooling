import dataclasses
import enum
import json
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path=None)

MAX_UINT256 = 2 ** 256 - 1


def get_env(name, required=True, default=None):
    value = os.getenv(name)

    def is_empty(v):
        return v is None or v.strip() == ""

    if is_empty(value) and not is_empty(default):
        value = default

    if is_empty(value) and required:
        raise Exception(f"Environment variable {name} is not set, see .env file")

    return value


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


def ask_user_string(prompt: str, default_answer: str | None = None, valid_answers: list[str] | None = None) -> str:
    default_str = f" [default: {default_answer}]" if default_answer else ""
    valid_answers = [answer.strip().lower() for answer in valid_answers] if valid_answers else []

    while True:
        answer = input(f"{prompt}{default_str}: ").strip().lower()

        if not answer and default_answer is not None:
            return default_answer
        elif answer and (not valid_answers or answer in valid_answers):
            return str(answer)
        else:
            continue

    assert False  # should not happen


# TODO LATER grace exit instead of exception
def ask_user_confirm_or_fail(prompt: str, default_answer=False):
    if not ask_user_confirm(prompt, default_answer):
        raise Exception("Operation cancelled by user")


# TODO LATER use click.confirm
# equivalent to "press enter to continue"
def ask_user_ok(prompt: str):
    _ = ask_user_string(f"{prompt} (OK)", default_answer="")


def ask_user_confirm(prompt: str, default_answer=False):
    default_str = "Y/n" if default_answer else "y/n" if default_answer is None else "y/N"

    while True:
        answer = input(f"{prompt} [{default_str}]: ").strip().lower()

        if answer == "" and default_answer is not None:
            return default_answer
        elif answer in ["y", "yes"]:
            return True
        elif answer in ["n", "no"]:
            return False
        else:
            continue


def json_dataclass(eq=True, init=True, **d_kwargs):
    def wrapper(cls):
        cls = dataclasses.dataclass(**d_kwargs, eq=eq, init=init)(cls)

        def __repr__(self):
            return json.dumps(
                dataclasses.asdict(self),
                indent=4,
                default=str
            )

        cls.__repr__ = __repr__
        return cls

    return wrapper


def json_pretty(json_data):
    def _json_pretty(data):
        if issubclass(type(data), enum.Enum):
            return data.name
        if hasattr(data, "__dict__") and data.__dict__:
            return _json_pretty(data.__dict__)
        if isinstance(data, list):
            return [_json_pretty(item) for item in data]
        if isinstance(data, dict) and data:
            return {key: _json_pretty(value) for key, value in data.items()}

        return data

    return json.dumps(_json_pretty(json_data), indent=4)


# converts 1100000000000000000 wei -> 1.1 ETH
def from_wei(amount: int | float, decimals: int) -> float:
    return amount / (10 ** decimals)


def str_from_wei(amount: int | float, decimals: int) -> str:
    return "{:.{}f}".format(from_wei(amount, decimals), decimals)  # cannot be f-string because decimals is dynamic


# converts 1.1 ETH -> 1100000000000000000 wei
def to_wei(amount: int | float, decimals: int) -> int:
    result = amount * (10 ** decimals)

    if result != int(result):
        raise ValueError(f"Precision lost: {result:.10f} != {int(result)}")

    return int(result)


def int_to_bytes(x: int, size: int = 32) -> bytes:
    if x < 0:
        raise ValueError("Cannot convert negative integer to bytes")
    return x.to_bytes(size, "big")


def int_from_bytes(xbytes: bytes) -> int:
    return int.from_bytes(xbytes, "big")


def private_str_to_log_str(private_str: str | None) -> str:
    if not private_str:
        return ""

    hex_padding = 2 if private_str.startswith("0x") else 0

    if len(private_str) > 65:
        return f"{private_str[:4 + hex_padding]}...{private_str[-4:]}"

    if len(private_str) > 40:
        return f"{private_str[:2 + hex_padding]}...{private_str[-2:]}"

    if len(private_str) > 20:
        return f"{private_str[:1 + hex_padding]}...{private_str[-1:]}"

    if len(private_str) > 5:
        return "*" * len(private_str)

    return "*" * 5


# converts Filecoin ID "f01234" to integer ID 1234
def f0_str_id_to_int(f_id: str | None) -> int | None:
    if f_id is None:
        return None

    if f_id.startswith("f0"):
        result = int(f_id[2:])
    else:
        result = int(f_id)

    if result < 1000:
        raise ValueError(f"Invalid f_id: {f_id}")

    return result


# converts integer ID 1234 to Filecoin ID "f01234"
def int_id_to_f0_str(int_id: int | None) -> str | None:
    if int_id is None:
        return None

    if int_id < 0:
        raise ValueError(f"Invalid int_id: {int_id}")

    return f"f0{int_id}"
