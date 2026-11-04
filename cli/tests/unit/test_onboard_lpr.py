import importlib
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import click

from cli.commands.repair_utils import RetrievalQuote

od = importlib.import_module("cli.commands.sp.onboard_data")

# `retrieval-client fetch` flags common to LPR main and v1-maintenance (v1-maintenance has no --pay-token-address)
RETRIEVAL_CLIENT_FETCH_FLAGS = {f"--{flag}" for flag in (
    "cid", "cid-file", "dry-run", "expires-in-sec", "filpay-private-key", "filpay-private-key-env", "filpay-private-key-file",
    "manifest", "no-progress", "out-dir", "parallel", "pay-debug", "pay-payments-address", "pay-rpc-url", "sp-base-url",
    "verbose", "yes")}


# real piece CIDs (deal 25): pieces land under their piece CID v2, the name Curio knows them by, not their storagePath
PIECES = [{"pieceCid": "baga6ea4seaqdtyojk7qurk2ikcf77xxcq4nb35luv6iixsvkyoqmrp65vyw7obq", "fileSize": 33500381452,
           "pieceSize": 34359738368, "storagePath": "baga6ea4seaqdtyojk7qurk2ikcf77xxcq4nb35luv6iixsvkyoqmrp65vyw7obq.car"},
          {"pieceCid": "baga6ea4seaqdowl43zhf5hy2b64ulwjdi3sogimkg7lula4aqdoylcnmnbdjyby", "fileSize": 18033180,
           "pieceSize": 33554432, "storagePath": "sub/renamed.car"}]
CID_V2 = ["bafkzcibg6t66fgicdy46dskx4fekwscqrp755yuhdio7k5fpscf4vkwdudel7xnofx3qm",
          "bafkzcibf4sv2gbyug5mxzxsol2prud5zixmsgrxe4mqyun6xiwbybag5qwe2y2cgtqdq"]


def test_lpr_download_saves_pieces_under_their_cid_v2(tmp_path, monkeypatch):
    commands = []

    def fake_run(command, **kwargs):  # retrieval-client stand-in: writes <cid>.car files into --out-dir
        commands.append(command)
        out_dir = tmp_path / "out"
        for cid in Path(command[command.index("--cid-file") + 1]).read_text(encoding="utf-8").split():
            (out_dir / f"{cid}.car").write_text("car")

    monkeypatch.setenv("RPC_URL", "https://rpc.example")
    monkeypatch.setattr(od, "get_retrieval_client_path", lambda: "retrieval-client")
    monkeypatch.setattr(od, "_ensure_payee_key", lambda deal, key_file: None)
    monkeypatch.setattr(od, "_quote_download", lambda pieces, host: RetrievalQuote(total=Decimal(1), paid_pieces=2, free_pieces=0))
    monkeypatch.setattr(od, "_ensure_repair_funded", lambda deal, quote, allow: None)
    monkeypatch.setattr(od, "_echo_download_summary", lambda pieces, no_summary: None)
    monkeypatch.setattr(od, "FileCoinPay", lambda: SimpleNamespace(address=lambda: "0xPay"))
    monkeypatch.setattr(od, "repair_payment_token", lambda deal: "0xToken")
    monkeypatch.setattr(od.utils, "confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(od.subprocess, "run", fake_run)

    (tmp_path / "out").mkdir()
    deal = SimpleNamespace(deal=SimpleNamespace(deal_id=7))
    with click.Context(od.onboard_data) as ctx:
        od._download_with_lpr(ctx, deal, PIECES, "https://sp.example", (tmp_path / "out").resolve(), True, None)

    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == sorted(CID_V2)

    # every flag passed must exist in all retrieval-client builds (LPR main and v1-maintenance)
    passed = {arg for arg in commands[0] if arg.startswith("--")}
    assert passed <= RETRIEVAL_CLIENT_FETCH_FLAGS, passed - RETRIEVAL_CLIENT_FETCH_FLAGS


def test_aria2_input_fetches_storage_paths_into_cid_v2_files(tmp_path, monkeypatch):
    monkeypatch.setattr(od, "_echo_download_summary", lambda pieces, no_summary: None)
    lines = od._write_aria2c_input_file(PIECES, "http://client.example:7777", tmp_path, True).read_text(encoding="utf-8").splitlines()

    assert lines[0::3] == [f"http://client.example:7777/piece/{PIECES[0]['pieceCid']}", "http://client.example:7777/piece/sub/renamed"]
    assert lines[1::3] == [f"  out={cid}" for cid in CID_V2]
