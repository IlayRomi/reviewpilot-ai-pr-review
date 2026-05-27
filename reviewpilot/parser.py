"""
Diff parser module.

Responsibility: Parse a unified diff file (.diff) into a list of structured
DiffFile objects. This is the entry point of the deterministic pipeline.

Supported format:
    Standard unified diff — the output of `git diff` or `git format-patch`.
    Headers beginning with "diff --git a/... b/..." are used as file boundaries.
    Binary files and mode-only changes are silently skipped (no hunks produced).

This module has zero AI involvement. All logic is deterministic and fully
testable with fixture strings or .diff files.

Public interface:
    parse_diff(path: Path) -> list[DiffFile]
        Read a .diff file from disk and return parsed DiffFile objects.

    parse_diff_text(diff_text: str) -> list[DiffFile]
        Parse diff text already in memory (used directly in tests).

Raises:
    ValueError — if diff_text is empty or contains no parseable files.
"""

from __future__ import annotations

import re
from pathlib import Path

from reviewpilot.models import ChangeType, DiffFile, DiffHunk, DiffLine, LineType


# Matches:  @@ -10,5 +10,7 @@  or  @@ -0,0 +1 @@  (count is optional, defaults to 1)
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_diff(path: Path) -> list[DiffFile]:
    """Read a unified diff file from disk and return a list of DiffFile objects.

    Args:
        path: Filesystem path to the .diff file.

    Returns:
        A list of DiffFile objects, one per changed file in the diff.

    Raises:
        ValueError: If the file cannot be read or contains no parseable files.
    """
    try:
        diff_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read diff file '{path}': {exc}") from exc
    return parse_diff_text(diff_text)


def parse_diff_text(diff_text: str) -> list[DiffFile]:
    """Parse unified diff text and return a list of DiffFile objects.

    Processes the diff line-by-line using a simple state machine:
      - "diff --git" lines mark the start of a new file section.
      - "--- " / "+++ " lines provide the old and new file paths.
      - "@@ " lines start a new hunk within the current file.
      - "+", "-", " " line prefixes determine LineType within a hunk.
      - All other lines (index, mode, rename, similarity) are ignored.

    Args:
        diff_text: Raw unified diff text as a string.

    Returns:
        A list of DiffFile objects. Each file has hunks populated with
        DiffLine objects and accurate additions/deletions counts.

    Raises:
        ValueError: If diff_text is empty (after stripping).
        ValueError: If no parseable files are found in the diff text.
    """
    if not diff_text.strip():
        raise ValueError("Diff text is empty")

    files: list[DiffFile] = []
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    pending_old_path: str | None = None  # set by "--- " line, consumed by "+++ " line

    for line in diff_text.splitlines():

        # ── New file boundary ─────────────────────────────────────────────
        if line.startswith("diff --git "):
            current_file, current_hunk = _flush_file(current_file, current_hunk, files)
            pending_old_path = None

        # ── Old path (--- a/path or --- /dev/null) ────────────────────────
        elif line.startswith("--- "):
            pending_old_path = _extract_path(line[4:], prefix="a/")

        # ── New path (+++ b/path or +++ /dev/null) — creates DiffFile ─────
        elif line.startswith("+++ "):
            new_path = _extract_path(line[4:], prefix="b/")
            change_type = _detect_change_type(pending_old_path, new_path)
            current_file = DiffFile(
                old_path=pending_old_path,
                new_path=new_path,
                change_type=change_type,
            )
            current_hunk = None

        # ── Hunk header (@@ -old +new @@) ────────────────────────────────
        elif line.startswith("@@"):
            if current_file is not None:
                if current_hunk is not None:
                    current_file.hunks.append(current_hunk)
                current_hunk = _parse_hunk_header(line)

        # ── Diff body lines (only meaningful inside a hunk) ───────────────
        elif current_file is not None and current_hunk is not None:
            if line.startswith("+"):
                current_hunk.lines.append(DiffLine(content=line, line_type=LineType.ADDED))
                current_file.additions += 1
            elif line.startswith("-"):
                current_hunk.lines.append(DiffLine(content=line, line_type=LineType.REMOVED))
                current_file.deletions += 1
            elif line.startswith(" "):
                current_hunk.lines.append(DiffLine(content=line, line_type=LineType.CONTEXT))
            # All other lines (e.g. "\ No newline at end of file") are skipped.

    # Flush the final file after the loop ends.
    _flush_file(current_file, current_hunk, files)

    if not files:
        raise ValueError("No parseable files found in diff")

    return files


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _flush_file(
    current_file: DiffFile | None,
    current_hunk: DiffHunk | None,
    files: list[DiffFile],
) -> tuple[None, None]:
    """Append the current hunk to the current file, add file to results list.

    Returns (None, None) so callers can reset both state variables in one line.
    """
    if current_file is not None:
        if current_hunk is not None:
            current_file.hunks.append(current_hunk)
        files.append(current_file)
    return None, None


def _extract_path(raw: str, prefix: str) -> str | None:
    """Strip the git path prefix and return the clean file path.

    Returns None for /dev/null (signals a file addition or deletion).

    Args:
        raw:    The text after "--- " or "+++ " (may have trailing whitespace).
        prefix: "a/" for old-path lines, "b/" for new-path lines.
    """
    raw = raw.strip()
    if raw == "/dev/null":
        return None
    if raw.startswith(prefix):
        return raw[len(prefix):]
    return raw


def _detect_change_type(old_path: str | None, new_path: str | None) -> ChangeType:
    """Derive ChangeType from the presence and equality of old and new paths."""
    if old_path is None and new_path is not None:
        return ChangeType.ADDED
    if new_path is None and old_path is not None:
        return ChangeType.DELETED
    if old_path is not None and new_path is not None:
        return ChangeType.RENAMED if old_path != new_path else ChangeType.MODIFIED
    return ChangeType.UNKNOWN


def _parse_hunk_header(line: str) -> DiffHunk:
    """Parse a @@ -old_start[,old_count] +new_start[,new_count] @@ line.

    When the count is omitted from the hunk header, git implies a count of 1.
    Falls back to a DiffHunk with all-None fields if the line is malformed.
    """
    match = _HUNK_HEADER_RE.match(line)
    if match:
        return DiffHunk(
            old_start=int(match.group(1)),
            old_count=int(match.group(2)) if match.group(2) is not None else 1,
            new_start=int(match.group(3)),
            new_count=int(match.group(4)) if match.group(4) is not None else 1,
        )
    # Malformed hunk header — return a hunk with unknown offsets.
    return DiffHunk(old_start=None, old_count=None, new_start=None, new_count=None)
