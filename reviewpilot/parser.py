"""
Diff parser module.

Responsibility: Parse a unified diff file (.diff) into a list of structured
DiffFile objects. This is the entry point of the deterministic pipeline.

Supported format:
    Standard unified diff — the output of `git diff` or `git format-patch`.
    Files starting with "diff --git" headers are supported.
    Binary files, submodule changes, and file mode-only changes are handled
    gracefully (skipped or flagged, never crash).

This module has zero AI involvement. All logic is deterministic and fully
testable with fixture .diff files.

Public interface (to be implemented in Commit #3):
    parse_diff(path: Path) -> list[DiffFile]
        Read a .diff file from disk and return parsed DiffFile objects.

    parse_diff_text(text: str) -> list[DiffFile]
        Parse diff text already loaded into memory (useful for tests).
"""

# Implementation will be added in Commit #3.
