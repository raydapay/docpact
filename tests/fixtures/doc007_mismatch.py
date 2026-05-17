"""Fixture for DOC007: Args section inconsistencies."""

from __future__ import annotations


def param_in_sig_absent_from_args(x: int, y: str) -> None:
    """Do something.

    Args:
        x: First param.
    """


def phantom_param_in_args(x: int) -> None:
    """Do something.

    Args:
        x: Real param.
        ghost: Does not exist in signature.
    """


def both_mismatches(x: int, y: str) -> None:
    """Do something.

    Args:
        x: Real param.
        phantom: Does not exist.
    """


def correct_args(x: int, y: str) -> None:
    """Do something.

    Args:
        x: First param.
        y: Second param.
    """


def varargs_not_required(x: int, *args: str, **kwargs: int) -> None:
    """Do something.

    Args:
        x: Required positional.
    """


def no_args_section(x: int, y: str) -> None:
    """Do something with no Args section at all."""


def empty_args_none(x: int) -> None:
    """Do something.

    Args:
        None.
    """
