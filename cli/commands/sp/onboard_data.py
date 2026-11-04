import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click
import humanfriendly
from hexbytes import HexBytes

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.repair_funding import FundingHistoryUnavailable, base_units_str, get_repair_funding, tokens_to_base_units
from cli.commands.repair_utils import (
    RetrievalQuote,
    SourceUnavailable,
    child_env,
    ensure_secret_file,
    dataset_hashes,
    find_healthy_source,
    get_retrieval_client_path,
    probe_piece,
    quote_retrieval,
    repair_payment_token,
    resolve_repair_payee,
    throwaway_key_file,
)
from cli.services.cid_converter import piece_cid_v1_to_v2
from cli.services.contracts.erc20_contract import ERC20Contract
from cli.services.contracts.evidence_adapter import EvidenceType
from cli.services.contracts.filecoin_pay import FileCoinPay
from cli.services.contracts.porep_market import PoRepMarket, PoRepMarketDealState
from cli.services.contracts.porep_market_view_helper import PoRepMarketDealView, PoRepMarketViewHelper
from cli.services.contracts.sector_evidence_adapter import SectorEvidenceAdapter
from cli.services.piece_set_commitment import PieceSet
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


def _echo_download_summary(pieces: list[dict], no_summary: bool):
    pieces_filesize_bytes = sum(piece.get("fileSize", 0) for piece in pieces)
    pieces_piecesize_bytes = sum(piece.get("pieceSize", 0) for piece in pieces)
    click.echo(f"Downloading {len(pieces)} .car files with total fileSize "
               f"{humanfriendly.format_size(pieces_filesize_bytes)} = {humanfriendly.format_size(pieces_filesize_bytes, binary=True)}, "
               f"{utils.bytes_to_sectors(pieces_piecesize_bytes, PoRepMarket().get_sector_size_bytes())} sectors" + (":" if not no_summary else ""))


# pieces are saved under their piece CID v2, the name Curio knows them by, whichever downloader fetched them
def _resolve_piece_output_file(piece: dict, output_dir: Path) -> Path:
    return (output_dir / piece_cid_v1_to_v2(piece["pieceCid"], piece["fileSize"])).resolve()


def _write_aria2c_input_file(pieces: list[dict], download_host: str, output_dir: Path, no_summary: bool) -> Path:
    with tempfile.NamedTemporaryFile(delete=False) as f:
        aria2_file = Path(f.name)

    _echo_download_summary(pieces, no_summary)

    with open(aria2_file, "w", encoding="utf-8") as f:
        for piece in pieces:
            output_file = _resolve_piece_output_file(piece, output_dir)
            download_url = f"{download_host}/piece/{piece['storagePath'].removesuffix('.car')}"

            f.write(f"{download_url}\n")
            f.write(f"  out={output_file.name}\n")
            f.write(f"  dir={output_file.parent}\n")

            if not no_summary:
                click.echo(f"  {download_url} -> {output_file} ({humanfriendly.format_size(piece['fileSize'])})")

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


# retrieval-client always writes <pieceCid>.car into --out-dir; move each piece to its piece CID v2 name
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
        raise click.UsageError("A paid repair download requires the deal payee private key: set --payee-key-file / SP_PAYEE_KEY_FILE "
                               "or FILPAY_PRIVATE_KEY")

    try:
        key_address = EthAddress.from_private_key(private_key if private_key.startswith("0x") else f"0x{private_key}")
    except ValueError as e:
        raise click.ClickException("Invalid payee private key") from e

    payee = resolve_repair_payee(deal)

    if key_address != payee:
        raise click.ClickException(f"Payee key address {key_address} does not match deal ID {deal.deal.deal_id} payee {payee}; "
                                   f"the repair retrieval is funded in the deal payee's FileCoinPay account.")


# exact quote of what is left to download, taken right before downloading it
def _quote_download(pieces: list[dict], download_host: str) -> RetrievalQuote:
    click.echo(f"\nQuoting {len(pieces)} piece(s) from {download_host}...")

    try:
        return quote_retrieval(download_host, [piece["pieceCid"] for piece in pieces])
    except SourceUnavailable as e:
        raise click.ClickException(f"Source {download_host} cannot serve the data: {e}") from e


# The client's deposit is the go-signal and the spending cap for a paid repair download: only start once the client's
# deposits not yet spent by the payee cover the quote.
def _ensure_repair_funded(deal, quote: RetrievalQuote, allow_unfunded_retrieval: bool):
    token = ERC20Contract(repair_payment_token(deal))
    token_decimals = token.decimals()
    token_symbol = token.symbol()

    def amount_str(amount: int) -> str:
        return f"{base_units_str(amount, token_decimals)} {token_symbol}"

    needed = tokens_to_base_units(quote.total, token_decimals)
    payee = resolve_repair_payee(deal)
    pay_command = f"`{sys.argv[0]} client pay-repair-retrieval {deal.deal.deal_id}`"

    try:
        funding = get_repair_funding(token.address(), deal.deal.client_address, payee, deal.deal.proposed_at_epoch)

    except FundingHistoryUnavailable as e:
        if not allow_unfunded_retrieval:
            raise click.ClickException(f"Could not check the client's repair funding of {payee}: {e}\n"
                                       f"Use an RPC_URL that serves logs back to epoch {deal.deal.proposed_at_epoch}, or re-run with "
                                       f"--allow-unfunded-retrieval to download anyway; whatever the deposits don't cover is paid "
                                       f"from the payee's own funds.") from e

        click.echo(f"WARNING: client funding could not be checked ({e}); downloading anyway (--allow-unfunded-retrieval).")
        return

    click.echo(f"Repair retrieval quote: {amount_str(needed)} for {quote.paid_pieces} paid piece(s)\n"
               f"  Client deposits to {payee} since the deal was proposed: {amount_str(funding.deposited)}\n"
               f"  Spent by {payee} on retrievals since then: {amount_str(funding.spent)}\n"
               f"  Available: {amount_str(funding.available)}")

    if funding.available >= needed:
        return

    shortfall = needed - funding.available

    if allow_unfunded_retrieval:
        click.echo(f"WARNING: client funding is short by {amount_str(shortfall)}; downloading anyway (--allow-unfunded-retrieval), "
                   f"so the rest is paid from the payee's own funds.")
        return

    raise click.ClickException(f"Waiting for client funding: quote {amount_str(needed)}, available {amount_str(funding.available)}, "
                               f"short {amount_str(shortfall)}. The client funds it with {pay_command}; re-run this command "
                               f"afterwards, or use --allow-unfunded-retrieval to pay the difference from the payee's own funds.")


AUTO_PROBE_PIECES = 3


# aria2 when the download host serves the pieces for free, as for any regular deal; otherwise this is a repair, fetched
# through retrieval-client (which also handles free sources), from a healthy SP unless --host is given
def _choose_downloader(pieces: list[dict], download_host: str) -> str:
    for piece in pieces[:AUTO_PROBE_PIECES]:
        piece_name = piece["storagePath"].removesuffix(".car")  # the URL aria2 would fetch
        probe = probe_piece(download_host, piece_name)

        if probe.status != "free":
            click.echo(f"{download_host} does not serve piece {piece_name} for free ({probe.detail or probe.status}); "
                       f"downloading through retrieval-client (FCSS repair).")
            return "lpr"

    click.echo(f"{download_host} serves the pieces for free; downloading with aria2.")
    return "aria2"


def _download_with_lpr(ctx,
                       deal,
                       pieces: list[dict],
                       download_host: str,
                       output_dir: Path,
                       no_summary: bool,
                       payee_key_file: str | None,
                       allow_unfunded_retrieval: bool = False):
    #
    retrieval_client_path = get_retrieval_client_path()
    quote = _quote_download(pieces, download_host)

    with contextlib.ExitStack() as stack:
        if quote.paid_pieces:
            _ensure_payee_key(deal, payee_key_file)
            _ensure_repair_funded(deal, quote, allow_unfunded_retrieval)
            key_file = payee_key_file
        else:
            # nothing to pay, so the payee key isn't needed
            click.echo(f"All {quote.free_pieces} piece(s) are free; downloading without the payee key.")
            key_file = str(stack.enter_context(throwaway_key_file()))

        _run_retrieval_client(ctx, retrieval_client_path, pieces, download_host, output_dir, no_summary, key_file)

    _move_lpr_downloads(pieces, output_dir)


def _run_retrieval_client(ctx,
                          retrieval_client_path: str,
                          pieces: list[dict],
                          download_host: str,
                          output_dir: Path,
                          no_summary: bool,
                          key_file: str | None):
    #
    cid_file = _write_lpr_cid_file(pieces, download_host, output_dir, no_summary)

    try:
        # pay through the same chain and FileCoinPay contract the client funded with `client pay-repair-retrieval`. The token
        # is USDFC (checked by _ensure_repair_funded): retrieval-client resolves it itself, from SP_PROXY_PAY_TOKEN_ADDRESS or
        # the chain default. Only pass flags every retrieval-client build has: --pay-token-address is missing from LPR's
        # v1-maintenance branch.
        defaults = {
            "--pay-rpc-url": utils.get_env_required("RPC_URL"),
            "--pay-payments-address": str(FileCoinPay().address()),
        }

        command = [retrieval_client_path, "fetch",
                   "--sp-base-url", download_host,
                   "--cid-file", str(cid_file),
                   "--out-dir", str(output_dir)]

        for option, value in defaults.items():
            if not any(arg == option or arg.startswith(f"{option}=") for arg in ctx.args):
                command += [option, value]

        # without a key file, retrieval-client reads the payee key from the FILPAY_PRIVATE_KEY env var
        if key_file:
            command += ["--filpay-private-key-file", str(Path(key_file).resolve())]

        command += ctx.args

        utils.confirm(f"\nRunning command:\n  {' '.join(command)}\nContinue?", default=True, abort=True)
        click.echo("\n")
        # the payee key is the only secret retrieval-client gets, and only when it comes from the environment
        subprocess.run(command, check=True, env=child_env(keep=() if key_file else ("FILPAY_PRIVATE_KEY",)))

    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"retrieval-client failed with exit code {e.returncode}; see its output above") from e

    finally:
        cid_file.unlink(missing_ok=True)


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
              help="Host to use for .car files download.  [default: same host as manifest URL; with lpr: a healthy SP "
                   "auto-detected from other providers' deals for the same dataset]")
@click.option("--port", default=7777, type=click.IntRange(min=1, max=65535), show_default=True,
              help="Port to use for .car files download from --host or the manifest URL host; not used when the source "
                   "is auto-detected (lpr).")
@click.option("--force", is_flag=True, default=False,
              help="Force download even if all DDO pieces are placed.  [default: false]")
@click.option("--no-summary", is_flag=True, default=False,
              help="Don't print the initial download summary.  [default: false]")
@click.option("--downloader", type=click.Choice(["auto", "aria2", "lpr"], case_sensitive=False), default="auto", show_default=True,
              help="Downloader to use: aria2 for free HTTP piece servers, lpr for large-paid-retrievals retrieval-client, "
                   "which pays sp-proxy quotes, also handles free servers and can auto-detect a healthy SP (FCSS repair). "
                   "auto uses aria2 when the download host serves sample pieces for free, else lpr.")
@click.option("--payee-key-file", envvar="SP_PAYEE_KEY_FILE", show_envvar=True, type=click.Path(exists=True, dir_okay=False),
              help="For paid lpr downloads: file with the private key of the deal's payee address (`sp register-sp --payee-address`), "
                   "passed to retrieval-client.  [default: FILPAY_PRIVATE_KEY env var]")
@click.option("--allow-unfunded-retrieval", is_flag=True, default=False,
              help="For paid lpr downloads: download even if the client's repair deposits don't cover the retrieval quote, or can't be "
                   "checked; the payee's own funds pay the rest.  [default: false]")
@click.pass_context
# TODO LATER add commP files verification after download
def onboard_data(ctx,
                 deal_id: int,
                 output_dir: str,
                 port: int,
                 host: str | None = None,
                 force: bool = False,
                 no_summary: bool = False,
                 downloader: str = "auto",
                 payee_key_file: str | None = None,
                 allow_unfunded_retrieval: bool = False):
    """
    \b
    Download data for a deal using aria2 downloader or large-paid-retrievals retrieval-client.

    \b
    Unknown [OPTIONS] are passed directly to aria2c / retrieval-client fetch, allowing for flexible configuration.
    See aria2c --help / retrieval-client fetch --help for available options.

    \b
    By default (--downloader auto) aria2 is used when the download host (--host:--port, else the manifest URL
    host) serves sample pieces for free, as for any regular deal; otherwise lpr.

    \b
    With lpr the data is fetched (and paid for if needed) from a large-paid-retrievals sp-proxy,
    paying from the deal payee's FileCoinPay account funded by the client (see `client pay-repair-retrieval`).
    Paid downloads only start once the client's deposits, less what the payee has spent on retrievals since
    the deal was proposed, cover the source's quote for the pieces still to download; free ones need no payee key.
    The source is a healthy SP found automatically (another provider's ACTIVE, PUBLIC deal for the same
    dataset whose piece endpoint serves the data), or --host:--port if given.

    \b
    Either way each piece is saved as <output-dir>/<piece CID v2>, the name Curio knows it by.

    DEAL_ID - The ID of the deal to download pieces for.

    \b
    See https://aria2.github.io/ and https://github.com/aria2/aria2 for more information about aria2 and installation instructions.
    See https://github.com/fidlabs/large-paid-retrievals for more information about retrieval-client.
    """

    SelfUpdateService.check_and_prompt(manual=False)

    # fail before anything else if the chosen downloader is missing
    if downloader == "aria2":
        _get_aria2c_path()
    elif downloader == "lpr":
        get_retrieval_client_path()

    click.echo("Fetching deal details...")
    deal = PoRepMarketViewHelper().get_deal_view(deal_id)
    manifest, raw_manifest = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)
    pieces = manifest[0]["pieces"]

    _validate_deal(deal, manifest)

    evidence_adapter = SectorEvidenceAdapter(deal.deal.evidence_adapter_address)
    cids_done = {row.piece_cid for row in PieceSet(pieces).rows
                 if evidence_adapter.is_piece_accepted(deal.deal.deal_id, row.index)}

    if len(cids_done) == len(pieces) and not force:
        click.echo(f"All {len(cids_done)} pieces of deal ID {deal_id} are placed; no need to download the data. Use --force to download anyway.")
        return

    click.echo(f"Found {len(pieces) - len(cids_done)} pieces not placed and {len(cids_done)} placed for deal ID {deal_id}, "
               f"{len(pieces)} total")

    pieces_done = [piece for piece in pieces if piece["pieceCid"] in cids_done]
    pieces_to_download = [piece for piece in pieces if piece not in pieces_done]

    if pieces_done and not force:
        click.echo(f"Skipping download of {len(pieces_done)} already placed pieces. Use --force to download them anyway.")

    _output_dir = Path(output_dir).resolve()
    _output_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest_file(manifest, _output_dir, deal_id)

    if host and not host.startswith(("http://", "https://")):
        host = f"http://{host}"

    parsed_url = commands_utils.validate_and_parse_url(host or deal.data.manifest_location)
    download_host = f"{parsed_url.scheme or 'http'}://{parsed_url.hostname}:{port}"

    if downloader == "auto":
        downloader = _choose_downloader(pieces_to_download if not force else pieces, download_host)

    if downloader == "lpr":
        if not host:
            download_host = find_healthy_source(dataset_hashes(manifest, raw_manifest), pieces, {deal.deal.provider_id}).base_url

        _download_with_lpr(ctx, deal, pieces_to_download if not force else pieces, download_host, _output_dir,
                           no_summary, payee_key_file, allow_unfunded_retrieval)
        return

    aria2c_path = _get_aria2c_path()
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

        utils.confirm(f"\nRunning command:\n  {' '.join(command)}\nContinue?", default=True, abort=True)
        click.echo("\n")
        subprocess.run(command, check=True)

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"aria2c failed with exit code {e.returncode}") from e

    finally:
        aria2_file.unlink(missing_ok=True)


def _validate_deal(deal: PoRepMarketDealView, manifest: list[dict]):
    commands_utils.ensure_deal_evidence_type(deal.deal, EvidenceType.SECTOR_PLACEMENT)

    if deal.deal.state not in (PoRepMarketDealState.ACCEPTED, PoRepMarketDealState.ACTIVE):
        raise click.ClickException(f"Deal ID {deal.deal.deal_id} is in state {deal.deal.state}, expected ACCEPTED or ACTIVE")

    piece_set = PieceSet(manifest[0]["pieces"])

    if piece_set.commitment() != deal.data.manifest_hash:
        raise click.ClickException(f"Manifest piece-set commitment {piece_set.commitment().to_0x_hex()} does not match deal ID "
                                   f"{deal.deal.deal_id} manifest hash {HexBytes(deal.data.manifest_hash).to_0x_hex()}")

    if piece_set.size_bytes != deal.terms.requested_size_bytes:
        raise click.ClickException(f"Manifest pieces size {piece_set.size_bytes} does not match deal ID {deal.deal.deal_id} "
                                   f"requested size {deal.terms.requested_size_bytes}")
