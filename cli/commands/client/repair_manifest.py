import sys
from pathlib import Path

import click

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.porep_market_view_helper import PoRepMarketViewHelper


@click.command()
@click.argument("deal_id", type=click.IntRange(min=1))
@click.option("--source-host", required=True,
              help="Hostname of the healthy SP machine serving the surviving copy (its large-paid-retrievals sp-proxy).")
@click.option("--manifest-port", type=click.IntRange(min=1, max=65535),
              help="Port the repair manifest will be hosted on at --source-host.  [default: same port as the original manifest URL]")
@click.option("--output-file", type=click.Path(dir_okay=False),
              help="File to write the repair manifest to.  [default: manifest_<DEAL_ID>.repair.json]")
def repair_manifest(deal_id: int, source_host: str, manifest_port: int | None = None, output_file: str | None = None):
    """
    Prepare a repair manifest for a deal whose data has to be re-onboarded from a healthy SP.

    \b
    1. Fetch the manifest of DEAL_ID (the deal being repaired),
    2. write it unchanged (same manifest hash) to --output-file,
    3. print the repair manifest URL: the original URL with its host rewritten to --source-host.

    `sp onboard-data` downloads pieces from the manifest URL host, so a deal proposed from the repair
    manifest URL makes the new SP fetch the data from the healthy SP. Host the written file at the printed
    URL, then run `client propose-deal <repair-manifest-url> --repair ...`.

    DEAL_ID - The ID of the deal being repaired.
    """

    deal = PoRepMarketViewHelper().get_deal_view(deal_id)
    _, raw_manifest = commands_utils.fetch_manifest(deal.data.manifest_location, show_manifest=False, retries=10)

    manifest_hash = commands_utils.hash_manifest(raw_manifest)
    if bytes(manifest_hash) != bytes(deal.data.manifest_hash):
        raise click.ClickException(f"Manifest currently served at {deal.data.manifest_location} does not match deal ID {deal_id} manifest hash")

    parsed_url = commands_utils.validate_and_parse_url(deal.data.manifest_location)
    port = manifest_port or parsed_url.port
    repair_manifest_url = parsed_url._replace(netloc=f"{source_host}:{port}" if port else source_host).geturl()

    _output_file = Path(output_file or f"manifest_{deal_id}.repair.json").resolve()
    if _output_file.exists():
        utils.confirm(f"File {_output_file} already exists. Overwrite?", abort=True)

    _output_file.write_bytes(raw_manifest)

    click.echo(utils.json_pretty({
        "repair_of_deal_id": deal_id,
        "original_manifest_url": deal.data.manifest_location,
        "repair_manifest_url": repair_manifest_url,
        "repair_manifest_file": str(_output_file),
        "manifest_hash": manifest_hash.to_0x_hex(),
    }))

    click.echo(f"\nHost {_output_file} at {repair_manifest_url}, then run "
               f"`{sys.argv[0]} client propose-deal {repair_manifest_url} --repair --repair-of {deal_id} ...`", err=True)
