import enum
import os
import json
import dataclasses

from dotenv import load_dotenv

load_dotenv()

MAX_UINT256 = 2 ** 256 - 1


def get_env(name, required=True, default=None):
    value = os.getenv(name)

    if not value and default is not None:
        value = default

    if required:
        if not value:
            raise Exception(f'Environment variable {name} is not set, see .env file (copy from .env.example)')

    return value


def string_to_bool(value: str) -> bool | None:
    if value is None: return None
    value = value.strip().lower()

    if value in ['true', '1', 'yes', 'y']:
        return True
    elif value in ['false', '0', 'no', 'n']:
        return False
    else:
        raise ValueError(f'Cannot convert string to bool: {value}')


def ask_user_string(prompt: str, default_value=None, valid_values=None):
    default_str = f' (default: {default_value})' if default_value else ''

    while True:
        answer = input(f'{prompt}{default_str}: ').strip()

        if not answer and default_value is not None:
            return default_value
        elif answer and (not valid_values or answer in valid_values):
            return answer
        else:
            continue


def ask_user_confirm_or_fail(prompt: str, default_answer=False):
    if not ask_user_confirm(prompt, default_answer):
        raise Exception('Operation cancelled by user')


def ask_user_confirm(prompt: str, default_answer=False):
    default_str = 'Y/n' if default_answer else 'y/n' if default_answer is None else 'y/N'

    while True:
        answer = input(f'{prompt} ({default_str}) ').strip().lower()

        if answer == '' and default_answer is not None:
            return default_answer
        elif answer in ['y', 'yes']:
            return True
        elif answer in ['n', 'no']:
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
        if hasattr(data, '__dict__') and data.__dict__:
            return _json_pretty(data.__dict__)
        if isinstance(data, list):
            return [_json_pretty(item) for item in data]
        if isinstance(data, dict) and data:
            return {key: _json_pretty(value) for key, value in data.items()}

        return data

    return json.dumps(_json_pretty(json_data), indent=4)


def to_tokens(amount: int, decimals: int):
    result = amount * (10 ** decimals)
    if int(result) != result:
        raise ValueError(f"Precision lost converting to tokens: {amount}e{decimals} = {result}")

    return int(result)


def from_tokens(amount: int, decimals: int):
    return amount * (10 ** decimals)


def int_to_bytes(x: int) -> bytes:
    if x < 0: raise ValueError("Cannot convert negative integer to bytes")
    return x.to_bytes((x.bit_length() + 7) // 8, 'big')


def int_from_bytes(xbytes: bytes) -> int:
    return int.from_bytes(xbytes, 'big')
