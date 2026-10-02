import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli.services.web3_service import EthAddress

# distinctive, not hex: a malformed "key" whose characters must never be echoed back
ENTRY_POINT = Path(__file__).resolve().parents[3] / "porep_tooling_cli.py"
MALFORMED_KEY = "0xmalformed-key-material-QWERTY-1234567890-should-never-be-printed"


def test_address_derivation_error_does_not_echo_the_key():
    with pytest.raises(ValueError) as error:
        EthAddress.from_private_key(MALFORMED_KEY)

    assert "QWERTY" not in str(error.value)


# client info --test-keys parses the key locally (sp/admin need the RPC first, so they can't reach parsing offline);
# the shared address-derivation error is covered by the test above
def test_malformed_key_is_not_printed_or_logged(tmp_path):
    group, env_var = "client", "CLIENT_PRIVATE_KEY"
    # run the real entry point, so the top-level error handler writes its log and traceback files
    log, error_log = tmp_path / "logs.log", tmp_path / "error.log"
    # RPC_URL is never contacted: the key is rejected while parsing, before any network call
    env = {**os.environ, env_var: MALFORMED_KEY, "RPC_URL": "http://127.0.0.1:9", "SKIP_SELF_UPDATE": "true",
           "_LOG_FILE": str(log), "_ERROR_LOG_FILE": str(error_log)}

    result = subprocess.run([sys.executable, str(ENTRY_POINT), group, "info", "--test-keys"],
                            env=env, capture_output=True, text=True, timeout=120, check=False)

    assert result.returncode != 0
    assert "Invalid private key" in result.stdout + result.stderr  # failed for the right reason
    for text in (result.stdout, result.stderr, log.read_text() if log.exists() else "", error_log.read_text() if error_log.exists() else ""):
        assert "QWERTY" not in text
