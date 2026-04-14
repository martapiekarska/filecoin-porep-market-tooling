import click

DRY_RUN: bool = False


@click.group(context_settings={"max_content_width": 180})
@click.option('--dry-run', envvar='DRY_RUN', show_envvar=True, is_flag=True, help="Enable dry-run mode, which only simulates transactions.", default=False)
def cli(dry_run: bool):
    global DRY_RUN
    DRY_RUN = dry_run


def is_dry_run() -> bool:
    return DRY_RUN
