import os

import pytest

from cli import utils


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
@pytest.mark.parametrize("content, mode, warns", [
    ("CLIENT_PRIVATE_KEY=placeholder-not-a-key\n", 0o644, True),
    ("SP_LOTUS_TOKEN=placeholder-not-a-token\n", 0o640, True),
    ("CLIENT_PRIVATE_KEY=placeholder-not-a-key\n", 0o600, False),
    ("CLIENT_PRIVATE_KEY=\nRPC_URL=https://example.com\n", 0o644, False),  # no secret values set
])
def test_dotenv_warning(tmp_path, monkeypatch, capsys, content, mode, warns):
    dotenv = tmp_path / ".env"
    dotenv.write_text(content)
    dotenv.chmod(mode)
    monkeypatch.setattr(utils, "DOTENV_PATH", str(dotenv))

    utils.warn_if_dotenv_exposed()

    err = capsys.readouterr().err
    assert ("WARNING" in err) == warns
    assert "placeholder-not-a" not in err
