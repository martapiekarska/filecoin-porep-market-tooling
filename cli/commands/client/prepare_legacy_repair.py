import sys
from pathlib import Path

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.commands.repair_utils import find_healthy_source, load_manifest_json, to_legacy_repair_manifest


@click.command()
@click.argument("original_manifest")
@click.option("--repair-source-url", required=True,
              help="Base URL of the healthy SP's piece server / large-paid-retrievals sp-proxy holding the data (e.g. https://sp.example.com:8787).")
@click.option("--output-file", type=click.Path(dir_okay=False),
              help="File to write the repair manifest to.  [default: repair_manifest_<dataset>.json]")
def prepare_legacy_repair(original_manifest: str, repair_source_url: str, output_file: str | None = None):
    """
    Prepare a manifest for a legacy (v1) dataset repair, with a manually chosen healthy source.

    \b
    1. Load ORIGINAL_MANIFEST and convert it to this CLI's manifest format if needed,
    2. embed --repair-source-url in it, so the new SP's `sp onboard-data` fetches the data from there,
    3. check the source serves every piece and show its exact retrieval quote (via retrieval-client),
    4. write the repair manifest; host it at any URL and run `client propose-deal <url> --repair-legacy`.

    \b
    ORIGINAL_MANIFEST - the dataset's original manifest: a local file, a manifest URL, or a
    toads.directory dataset page URL (e.g. https://toads.directory/dataset/<id>). Both this CLI's manifest
    format and data-prep-standard super-manifests whose contents are the pieces' CAR files are supported.
    """

    manifest = to_legacy_repair_manifest(load_manifest_json(original_manifest), repair_source_url)
    name = str(manifest[0].get("dataset", {}).get("name") or "legacy").replace("/", "_").replace(" ", "_")

    _output_file = Path(output_file or f"repair_manifest_{name}.json").resolve()
    if _output_file.exists():
        utils.confirm(f"File {_output_file} already exists. Overwrite?", abort=True)

    _output_file.write_text(utils.json_pretty(manifest), encoding="utf-8")
    manifest, _ = commands_utils.fetch_local_manifest(_output_file)  # validate the result like any other manifest
    pieces = manifest[0]["pieces"]

    source = find_healthy_source(b"", pieces, set(), repair_source_url, probe_fallback=True)

    cost_str = "0 (the source serves the data for free)" if source.is_free() else \
        f"{source.quote.total} USDFC for {source.quote.paid_pieces} paid piece(s)"

    click.echo(f"\nRepair manifest written to {_output_file}\n"
               f"  Pieces: {len(pieces)}\n"
               f"  Repair source: {source.base_url}\n"
               f"  Retrieval cost quoted by the source: {cost_str}\n"
               f"\nHost it at any URL, then run "
               f"`{sys.argv[0]} client propose-deal <manifest-url> --repair-legacy --repair-source-url {source.base_url} ...`")
