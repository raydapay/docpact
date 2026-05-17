"""CLI entry point.

Implements the commands defined in spec §16: check, generate, show-schema,
list-rules. v0.1 ships with check (including --fix and --unsafe-fixes) as
the primary surface.

Implementation notes:
    Uses click for subcommands. argparse was considered (stdlib, no
    dependencies) but click's ergonomics for subcommands with shared options
    are materially better for a tool with this command surface.
"""

from __future__ import annotations

import click


@click.group()
@click.version_option()
def main() -> None:
    """docpact — docstring contract validator."""


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--fix", is_flag=True, help="Apply safe fixes in-place.")
@click.option("--unsafe-fixes", is_flag=True, help="Apply unsafe fixes. Requires --fix.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
def check(paths: tuple[str, ...], fix: bool, unsafe_fixes: bool, output_format: str) -> None:
    """Check docstrings against the configured schema."""
    raise NotImplementedError("check command not yet implemented")


@main.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
def generate(paths: tuple[str, ...]) -> None:
    """Generate stub docstrings for undocumented functions."""
    raise NotImplementedError("generate command not yet implemented")


@main.command(name="show-schema")
@click.option("--tier", type=click.IntRange(1, 4), required=True)
def show_schema(tier: int) -> None:
    """Print the schema requirements for a given tier."""
    raise NotImplementedError("show-schema command not yet implemented")


@main.command(name="list-rules")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
def list_rules(output_format: str) -> None:
    """List all defined rules with their default severity."""
    raise NotImplementedError("list-rules command not yet implemented")


if __name__ == "__main__":
    main()
