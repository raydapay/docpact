"""Fixture for FIX004: suppression comments not on def/class keyword lines."""

from __future__ import annotations


# Correct placement — nodo on the def line; no FIX004 expected.
def correct_on_def(  # nodo: DOC012 -- correct placement
    arg: str,
) -> None:
    pass


# Correct placement — nodo on an async def line.
async def correct_async(  # nodo: DOC012 -- correct placement
    arg: str,
) -> None:
    pass


# Correct placement — nodo on a class line.
class CorrectClass:  # nodo: DOC003 -- correct placement
    pass


# Misplaced — ruff moved the comment to the closing ) -> None: line.
def misplaced_closing_paren(
    arg: str,
) -> None:  # nodo: DOC012 -- ruff moved this here
    pass


# Misplaced — comment on a decorator line.
@staticmethod  # nodo: DOC012 -- this is a decorator, not a def line
def misplaced_on_decorator(arg: str) -> None:
    pass


# Misplaced — comment on a regular body line, not a def line.
def misplaced_on_body_line(arg: str) -> None:
    x = 1  # nodo: DOC012 -- this is inside the function body
    return None
