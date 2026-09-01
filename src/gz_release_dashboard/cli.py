"""Command line entry point."""

from __future__ import annotations

import click

from . import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="gz-dashboard")
def main() -> None:
    """Track Gazebo library versions across every packaging system."""


if __name__ == "__main__":  # pragma: no cover
    main()
