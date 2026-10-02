import click
import pytest

from cli.services.web3_service import lotus_signing_url


@pytest.mark.parametrize("rpc_url, lotus_rpc_url, expected", [
    ("http://127.0.0.1:1234/rpc/v1", None, "http://127.0.0.1:1234/rpc/v1"),  # local node as RPC_URL
    ("http://10.0.0.5:1234/rpc/v1", None, "http://10.0.0.5:1234/rpc/v1"),  # private network node
    ("https://1.1.1.1/rpc/v1", "https://8.8.4.4/rpc/v1", "https://8.8.4.4/rpc/v1"),  # explicit remote node over https
    ("https://1.1.1.1/rpc/v1", "http://127.0.0.1:1234/rpc/v1", "http://127.0.0.1:1234/rpc/v1"),
])
def test_token_goes_to_the_users_own_node(monkeypatch, rpc_url, lotus_rpc_url, expected):
    monkeypatch.setenv("RPC_URL", rpc_url)
    if lotus_rpc_url:
        monkeypatch.setenv("LOTUS_RPC_URL", lotus_rpc_url)
    else:
        monkeypatch.delenv("LOTUS_RPC_URL", raising=False)

    assert lotus_signing_url() == expected


def test_token_never_goes_to_a_public_rpc_url(monkeypatch):
    monkeypatch.setenv("RPC_URL", "https://1.1.1.1/rpc/v1")  # e.g. the public endpoint in .env.mainnet
    monkeypatch.delenv("LOTUS_RPC_URL", raising=False)

    with pytest.raises(click.ClickException, match="set LOTUS_RPC_URL"):
        lotus_signing_url()


def test_token_never_sent_in_cleartext_over_the_internet(monkeypatch):
    monkeypatch.setenv("RPC_URL", "http://127.0.0.1:1234/rpc/v1")
    monkeypatch.setenv("LOTUS_RPC_URL", "http://8.8.4.4:1234/rpc/v1")

    with pytest.raises(click.ClickException, match="must use https"):
        lotus_signing_url()
