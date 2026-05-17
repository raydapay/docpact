"""Diagnostic and fix types — the output of rule evaluation.

Spec §7.3 defines the rule signature. Rules return `list[RuleResult]`.
The fix engine consumes `Fix` objects separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Severity(StrEnum):
    """Diagnostic severity."""

    ERROR = "error"
    WARNING = "warning"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Position in a source file."""

    file_path: Path
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class Fix:
    """A single source modification.

    Fixes are text-level edits with explicit byte ranges. The fix engine
    applies them with conflict detection (no two fixes may modify
    overlapping ranges).
    """

    description: str  # human-readable explanation of what the fix does
    file_path: Path
    start_offset: int  # byte offset, inclusive
    end_offset: int  # byte offset, exclusive
    replacement: str


@dataclass(frozen=True, slots=True)
class RuleResult:
    """A single diagnostic emitted by a rule.

    The code identifies the rule. The message is the user-facing
    explanation. fix and unsafe_fix are optional — at most one of each
    may be present.
    """

    code: str  # e.g., "DOC007", "MCP001"
    severity: Severity
    message: str
    location: SourceLocation
    fix: Fix | None = None
    unsafe_fix: Fix | None = None
