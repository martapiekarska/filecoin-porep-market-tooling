import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import humanfriendly

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.repair_utils import (
    ensure_secret_file,
    find_healthy_source,
    get_manifest_repair_source,
    repair_payment_token,
    resolve_repair_payee,
)
from cli.commands.sp.claim_allocations import claim_allocations as claim_allocations_command
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.porep_market import PoRepMarket, PoRepMarketDealState
from cli.services.contracts.porep_market_view_helper import PoRepMarketViewHelper
from cli.services.self_update import SelfUpdateService
from cli.services.web3_service import EthAddress


def _get_aria2c_path() -> str:
    aria2c_path = utils.get_env_required("ARIA2C_PATH", default="aria2c")

    if aria2c_path != "aria2c":
        aria2c_path = Path(aria2c_path).resolve()

    # noinspection PyBroadException
    try:
        subprocess.run([aria2c_path, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # pylint: disable=broad-exception-caught
    except Exception as e:
        click.echo("aria2c not found. Please install aria2c to use this command.\n"
                   "See https://aria2.github.io/ and https://github.com/aria2/aria2 for more information.\n"
                   "Set the ARIA2C_PATH environment variable if aria2c is installed but not in PATH.\n"
                   "The easiest installation method is using the terminal:\n"
                   "run sudo apt install aria2 (Debian/Ubuntu), sudo dnf install aria2 (Fedora), or sudo pacman -S aria2 (Arch).\n")

        raise click.ClickException(f"{aria2c_path} not found:\n{e}") from e

    return str(aria2c_path)


def _get_retrieval_client_path() -> str:
    retrieval_client_path = utils.get_env_required("RETRIEVAL_CLIENT_PATH", default="retrieval-client")

    if retrieval_client_path != "retrieval-client":
        retrieval_client_path = Path(retrieval_client_path).resolve()

    # noinspection PyBroadException
    try:
        subprocess.run([retrieval_client_path, "fetch", "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # pylint: disable=broad-exception-caught
    except Exception as e:
        click.echo("retrieval-client not found. Please install large-paid-retrievals retrieval-client to use --downloader lpr.\n"
                   "See https://github.com/fidlabs/large-paid-retrievals#for-dataset-consumers for installation instructions:\n"
                   "  git clone https://github.com/fidlabs/large-paid-retrievals && cd large-paid-retrievals && "
                   "go build -o bin/retrieval-client ./cmd/retrieval-client\n"
                   "Set the RETRIEVAL_CLIENT_PATH environment variable if retrieval-client is installed but not in PATH.\n")

        raise click.ClickException(f"{retrieval_client_path} not found:\n{e}") from e

    return str(retrieval_client_path)


def _echo_download_summary(pieces: list[dict], no_summary: bool):
    pieces_filesize_bytes = sum(piece.get("fileSize", 0) for piece in pieces)
    pieces_piecesize_bytes = sum(piece.get("pieceSize", 0) for piece in pieces)
    click.echo(f"Downloading {len(pieces)} .car files with total fileSize "
               f"{humanfriendly.format_size(pieces_filesize_bytes)} = {humanfriendly.format_size(pieces_filesize_bytes, binary=True)}, "
               f"{utils.bytes_to_sectors(pieces_piecesize_bytes, PoRepMarket().get_sector_size_bytes())} sectors" + (":" if not no_summary else ""))


def _resolve_piece_output_file(piece: dict, output_dir: Path) -> Path:
    storage_path = piece["storagePath"]
    output_file = (output_dir / storage_path).resolve()

    # disallow path traversal outside of the output directory
    if output_dir not in output_file.parents:
        raise click.ClickException(f"Invalid manifest piece storagePath: {storage_path}")

    return output_file


def _write_aria2c_input_file(pieces: list[dict], download_host: str, output_dir: Path, no_summary: bool) -> Path:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        aria2_file = Path(f.name)

    _echo_download_summary(pieces, no_summary)

    with open(aria2_file, "w", encoding="utf-8") as f:
        for piece in pieces:
            output_file = _resolve_piece_output_file(piece, output_dir)
            piece_name = piece["storagePath"].removesuffix(".car")

            download_url = f"{download_host}/piece/{piece_name}"

            f.write(f"{download_url}\n")
            f.write(f"  out={output_file.name}\n")
            f.write(f"  dir={output_file.parent}\n")

            if not no_summary:
                click.echo(f"  {download_url} -> {output_file}")

    if not no_summary:
        click.echo("(use --no-summary to skip this summary)")
        click.echo("\n")

    return aria2_file.resolve()


def _write_lpr_cid_file(pieces: list[dict], download_host: str, output_dir: Path, no_summary: bool) -> Path:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        cid_file = Path(f.name)

    _echo_download_summary(pieces, no_summary)

    with open(cid_file, "w", encoding="utf-8") as f:
        for piece in pieces:
            output_file = _resolve_piece_output_file(piece, output_dir)
            f.write(f"{piece['pieceCid']}\n")

            if not no_summary:
                click.echo(f"  {download_host}/piece/{piece['pieceCid']} (large-paid-retrievals) -> {output_file}")

    if not no_summary:
        click.echo("(use --no-summary to skip this summary)")
        click.echo("\n")

    return cid_file.resolve()


# retrieval-client always writes <pieceCid>.car into --out-dir; move each piece to its manifest storagePath
def _move_lpr_downloads(pieces: list[dict], output_dir: Path) -> list[tuple[dict, Path]]:
    result = []

    for piece in pieces:
        downloaded_file = output_dir / f"{piece['pieceCid']}.car"
        output_file = _resolve_piece_output_file(piece, output_dir)

        if not downloaded_file.exists():
            raise click.ClickException(f"retrieval-client did not produce {downloaded_file}")

        if downloaded_file.resolve() != output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            downloaded_file.replace(output_file)

        result.append((piece, output_file))

    return result


# retrieval-client pays from the deal payee's FileCoinPay account, which the client funded with `client pay-repair-retrieval`;
# fail before spending anything if the key does not belong to that payee
def _ensure_payee_key(deal, payee_key_file: str | None):
    if payee_key_file:
        # the payee also receives the SP's deal revenue, so treat its key like an SSH private key
        ensure_secret_file(Path(payee_key_file), "payee key file")
        private_key = Path(payee_key_file).read_text(encoding="utf-8").strip()
    elif os.getenv("FILPAY_PRIVATE_KEY"):
        click.echo("WARNING: FILPAY_PRIVATE_KEY exposes the payee key, which also receives your deal revenue, to every process "
                   "started from this environment; prefer --payee-key-file with a chmod 600 file.")
        private_key = os.environ["FILPAY_PRIVATE_KEY"].strip()
    else:
        raise click.UsageError("--downloader lpr requires the deal payee private key: set --payee-key-file / SP_PAYEE_KEY_FILE or FILPAY_PRIVATE_KEY")

    try:
        key_address = EthAddress.from_private_key(private_key if private_key.startswith("0x") else f"0x{private_key}")
    except ValueError as e:
        raise click.ClickException("Invalid payee private key") from e

    payee = resolve_repair_payee(deal)

    if key_address != payee:
        raise click.ClickException(f"Payee key address {key_address} does not match deal ID {deal.deal.deal_id} payee {payee}; "
                                   f"the repair retrieval is funded in the deal payee's FileCoinPay account.")


def _download_with_lpr(ctx,
                       deal,
                       pieces: list[dict],
                       download_host: str,
                       output_dir: Path,
                       no_summary: bool,
                       payee_key_file: str | None,
                       claim_allocations: str | None):
    #
    retrieval_client_path = _get_retrieval_client_path()
    _ensure_payee_key(deal, payee_key_file)
    cid_file = _write_lpr_cid_file(pieces, download_host, output_dir, no_summary)

    try:
        # pay through the same chain, FileCoinPay contract and token the client funded with `client pay-repair-retrieval`
        defaults = {
            "--pay-rpc-url": utils.get_env_required("RPC_URL"),
            "--pay-payments-address": str(FileCoinPay().address()),
            "--pay-token-address": str(repair_payment_token(deal)),
        }

        command = [retrieval_client_path, "fetch",
                   "--sp-base-url", download_host,
                   "--cid-file", str(cid_file),
                   "--out-dir", str(output_dir)]

        for option, value in defaults.items():
            if not any(arg == option or arg.startswith(f"{option}=") for arg in ctx.args):
                command += [option, value]

        # without --payee-key-file, retrieval-client reads its key from the FILPAY_PRIVATE_KEY env var
        if payee_key_file:
            command += ["--filpay-private-key-file", str(Path(payee_key_file).resolve())]

        command += ctx.args

        utils.confirm(f"\nRunning command:\n  {' '.join(command)}\nContinue?", default=True, abort=True)
        click.echo("\n")
        subprocess.run(command, check=True)

    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"retrieval-client failed with exit code {e.returncode}; see its output above") from e

    finally:
        cid_file.unlink(missing_ok=True)

    downloaded = _move_lpr_downloads(pieces, output_dir)

    if claim_allocations:
        for piece, output_file in downloaded:
            ctx.invoke(claim_allocations_command, software=claim_allocations, deal_id=deal.deal.deal_id,
                       cars_dir=str(output_file.parent), cid=piece["pieceCid"])


def _write_manifest_file(manifest: list[dict], output_dir: Path, deal_id: int) -> Path:
    click.echo()
    manifest_file = output_dir / f"manifest_{deal_id}.json"

    if manifest_file.exists():
        with open(manifest_file, "r", encoding="utf-8") as f:
            existing_manifest = json.load(f)

        if utils.json_pretty(existing_manifest, True) != utils.json_pretty(manifest, True):
            utils.confirm(f"A different manifest already exists in the output directory: {manifest_file}\n"
                          "Do you want to overwrite it?", abort=True)

    with open(manifest_file, "w", encoding="utf-8") as f:
        f.write(utils.json_pretty(manifest))

    click.echo(f"Deal manifest saved to {manifest_file}\n")
    return manifest_file.resolve()


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("deal_id", type=click.IntRange(min=1))
@click.option("--output-dir", type=click.Path(file_okay=False), required=True,
              help="Directory to save downloaded pieces.")
@click.option("--host",
              help="Host to use for .car files download.  [default: the manifest's repair source for legacy repairs, else same host "
                   "as manifest URL; with --downloader lpr: a healthy SP auto-detected from other providers' deals for the same dataset]")
@click.option("--port", default=7777, type=click.IntRange(min=1, max=65535), show_default=True,
              help="Port to use for .car files download.")
@click.option("--force", is_flag=True, default=False,
              help="Force download even if all allocations are claimed.  [default: false]")
@click.option("--no-summary", is_flag=True, default=False,
              help="Don't print the initial download summary.  [default: false]")
@click.option("--claim-allocations", type=click.Choice(["curio", "boost"], case_sensitive=False),
              help="Claim allocation(s) for each piece right after download using specified software.  [default: none]")
@click.option("--downloader", type=click.Choice(["aria2", "lpr"], case_sensitive=False), default="aria2", show_default=True,
              help="Downloader to use: aria2 for free HTTP piece servers, lpr for paid retrieval from a "
                   "large-paid-retrievals sp-proxy (e.g. FCSS repair from a healthy SP).")
@click.option("--payee-key-file", envvar="SP_PAYEE_KEY_FILE", show_envvar=True, type=click.Path(exists=True, dir_okay=False),
              help="With --downloader lpr: file with the private key of the deal's payee address (`sp register-sp --payee-address`), "
                   "passed to retrieval-client.  [default: FILPAY_PRIVATE_KEY env var]")
@click.pass_context
# TODO LATER add commP files verification after download
def onboard_data(ctx,
                 deal_id: int,
                 output_dir: str,
                 port: int,
                 host: str | None = None,
                 force: bool = False,
                 no_summary: bool = False,
                 claim_allocations: str | None = None,
                 downloader: str = "aria2",
                 payee_key_file: str | None = None):
    """
    \b
    Download data for a deal using aria2 downloader or large-paid-retrievals retrieval-client.

    \b
    Unknown [OPTIONS] are passed directly to aria2c / retrieval-client fetch, allowing for flexible configuration.
    See aria2c --help / retrieval-client fetch --help for available options.

    \b
    With --downloader lpr the data is fetched (and paid for if needed) from a large-paid-retrievals sp-proxy,
    paying from the deal payee's FileCoinPay account funded by the client (see `client pay-repair-retrieval`).
    The source is a healthy SP found automatically (another provider's ACTIVE, PUBLIC deal for the same
    dataset whose piece endpoint serves the data), or --host:--port if given.

    \b
    For legacy (v1) repairs the source embedded in the deal manifest (`client prepare-legacy-repair`)
    is used by both downloaders unless --host is given.

    DEAL_ID - The ID of the deal to download pieces for.

    \b
    See https://aria2.github.io/ and https://github.com/aria2/aria2 for more information about aria2 and installation instructions.
    See https://github.com/fidlabs/large-paid-retrievals for more information about retrieval-client.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    aria2c_path = _get_aria2c_path() if downloader == "aria2" else None

    click.echo("Fetching deal details...")
    deal = PoRepMarketViewHelper().get_deal_view(deal_id)

    if deal.deal.state not in (PoRepMarketDealState.ACCEPTED, PoRepMarketDealState.ACTIVE):
        raise click.ClickException(f"Deal ID {deal_id} is in state {deal.deal.state}, expected ACCEPTED or ACTIVE")

    deal_allocations = commands_utils.get_deal_allocations(deal.deal)
    deal_claims = commands_utils.get_deal_claims(deal.deal)
    allocations_not_claimed = {allocation_id: alloc for allocation_id, alloc in deal_allocations.items() if str(allocation_id) not in deal_claims}
    cids_claimed = [claim.get("Data", {}).get("/") for claim in deal_claims.values()]

    if deal_claims and not allocations_not_claimed and not force:
        click.echo(f"All {len(deal_claims)} allocations for deal ID {deal_id} are claimed; no need to download the data. Use --force to download anyway.")
        return

    if not deal_claims and not allocations_not_claimed:
        raise click.ClickException(f"No allocations found for deal ID {deal_id} but deal in {deal.deal.state} state.")

    click.echo(f"Found {len(allocations_not_claimed)} allocations not claimed and {len(deal_claims)} claims for deal ID {deal_id}, "
               f"{len(deal_allocations) + len(deal_claims)} total")

    manifest, _ = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)
    pieces = manifest[0]["pieces"]
    pieces_claimed = [piece for piece in pieces if piece["pieceCid"] in cids_claimed]
    pieces_to_download = [piece for piece in pieces if piece not in pieces_claimed]

    if pieces_claimed and not force:
        click.echo(f"Skipping download of {len(pieces_claimed)} already claimed pieces. Use --force to download them anyway.")

    _output_dir = Path(output_dir).resolve()
    _output_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest_file(manifest, _output_dir, deal_id)

    if host and not host.startswith(("http://", "https://")):
        host = f"http://{host}"

    parsed_url = commands_utils.validate_and_parse_url(host or deal.data.manifest_location)
    download_host = f"{parsed_url.scheme or 'http'}://{parsed_url.hostname}:{port}"
    repair_source = get_manifest_repair_source(manifest)

    if not host and repair_source:
        click.echo(f"Using repair source from the deal manifest: {repair_source}")
        download_host = repair_source

    if downloader == "lpr":
        if not host and not repair_source:
            download_host = find_healthy_source(deal.data.manifest_hash, pieces, {deal.deal.provider_id}).base_url

        _download_with_lpr(ctx, deal, pieces_to_download if not force else pieces, download_host, _output_dir,
                           no_summary, payee_key_file, claim_allocations)
        return

    if not aria2c_path:
        raise RuntimeError("aria2c path not resolved")

    aria2_file = _write_aria2c_input_file(pieces_to_download if not force else pieces, download_host, _output_dir, no_summary)

    try:
        command = [aria2c_path,
                   "-i", str(aria2_file),
                   "-x", "16",
                   "-s", "16",
                   "--continue=true",
                   "--auto-file-renaming=false",
                   "--summary-interval=30",
                   "--console-log-level=warn"] + ctx.args

        if claim_allocations:
            callback_path = Path(sys.argv[0]).parent / "cli" / "commands" / "sp" / "_aria2_callback.py"
            command += [f"--on-download-complete={callback_path}"]

            env = {
                **os.environ,
                "ARIA2C_CLAIM_ALLOCATIONS_SOFTWARE": claim_allocations,
                "ARIA2C_DEAL_ID": str(deal_id),
            }
        else:
            env = None  # default argument

        utils.confirm(f"\nRunning command:\n  {' '.join(command)}\nContinue?", default=True, abort=True)
        click.echo("\n")
        subprocess.run(command, check=True, env=env)

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"aria2c failed with exit code {e.returncode}") from e

    finally:
        aria2_file.unlink(missing_ok=True)
