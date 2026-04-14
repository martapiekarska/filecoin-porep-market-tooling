from cli import commands
from ._cli import cli

# noinspection PyTypeChecker
cli.add_command(commands.admin)

# noinspection PyTypeChecker
cli.add_command(commands.client)

# noinspection PyTypeChecker
cli.add_command(commands.sp)

# noinspection PyTypeChecker
cli.add_command(commands.info)
