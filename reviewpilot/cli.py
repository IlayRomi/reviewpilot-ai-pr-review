"""
CLI entry point for ReviewPilot.

Usage:
    python -m reviewpilot <diff_file> [--output PATH] [--title TITLE] [--mock-ai]
    reviewpilot <diff_file> [--output PATH] [--title TITLE] [--mock-ai]

Arguments:
    diff_file       Path to a unified diff file (.diff) to analyze.

Options:
    --output PATH   Write the Markdown report to a file instead of stdout.
    --title TITLE   Custom report title (default: "ReviewPilot Report — <filename>").
    --mock-ai       Force use of MockAIClient (default in MVP — always active).
    -h, --help      Show this help message and exit.

Exit codes:
    0   Success.
    1   Error (file not found, invalid diff, output write failure).

Design notes:
    - Uses argparse from the Python standard library only.
    - Raw diff text is read from disk; the pipeline never receives it via the CLI
      interface directly (it passes through build_report_from_file).
    - Errors are written to stderr; the Markdown report goes to stdout or a file.
    - The --mock-ai flag is accepted for forward compatibility. In the current MVP
      the MockAIClient is always used regardless of this flag.

Public interface:
    main() -> None
        Parse arguments, run the full analysis pipeline, write or print the report.
        Called by the `reviewpilot` console script entry point and by __main__.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reviewpilot.report_builder import build_report_from_file
from reviewpilot.renderer import render_markdown, render_to_file

_DEFAULT_TITLE_PREFIX = "ReviewPilot Report"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and run the ReviewPilot analysis pipeline.

    Reads a unified diff file, builds a ReviewReport, then either writes
    the Markdown report to a file (--output) or prints it to stdout.

    Exits with code 1 and writes a message to stderr on any error.
    """
    args = _build_parser().parse_args()
    _execute(args)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Construct and return the argparse.ArgumentParser for ReviewPilot."""
    parser = argparse.ArgumentParser(
        prog="reviewpilot",
        description=(
            "ReviewPilot — AI-assisted PR review and test planning.\n"
            "Analyzes a unified diff file and produces a structured Markdown report."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reviewpilot changes.diff\n"
            "  reviewpilot changes.diff --output report.md\n"
            "  reviewpilot changes.diff --title 'Sprint 42 Review' --output report.md\n"
            "  python -m reviewpilot changes.diff"
        ),
    )
    parser.add_argument(
        "diff_file",
        metavar="diff_file",
        help="Path to a unified diff file (output of `git diff`) to analyze.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help=(
            "Write the Markdown report to this file instead of stdout. "
            "The file is created or overwritten."
        ),
    )
    parser.add_argument(
        "--title",
        metavar="TITLE",
        default=None,
        help=(
            "Custom report title. "
            f"Defaults to '{_DEFAULT_TITLE_PREFIX} — <filename>'."
        ),
    )
    parser.add_argument(
        "--mock-ai",
        action="store_true",
        default=False,
        help=(
            "Force use of MockAIClient (offline, deterministic). "
            "This is the default in the current MVP and this flag is always active."
        ),
    )
    return parser


def _execute(args: argparse.Namespace) -> None:
    """Core execution logic after argument parsing.

    Separated from main() so it can be called directly in tests without
    patching sys.argv.

    Args:
        args: Parsed namespace from argparse.

    Raises:
        SystemExit(1): On any unrecoverable error.
    """
    diff_path = Path(args.diff_file)

    # ── Validate input path ──────────────────────────────────────────────
    if not diff_path.exists():
        _die(f"diff file not found: {diff_path}")
    if not diff_path.is_file():
        _die(f"path is not a file: {diff_path}")

    # ── Build title ──────────────────────────────────────────────────────
    title = args.title or f"{_DEFAULT_TITLE_PREFIX} — {diff_path.name}"

    # ── Run analysis pipeline ─────────────────────────────────────────────
    try:
        report = build_report_from_file(diff_path, ai_client=None, title=title)
    except ValueError as exc:
        _die(str(exc))

    # ── Render and output ─────────────────────────────────────────────────
    if args.output:
        output_path = Path(args.output)
        try:
            render_to_file(report, output_path)
        except OSError as exc:
            _die(f"cannot write output file '{output_path}': {exc}")
        # Confirm written — goes to stderr so it doesn't pollute stdout redirects.
        print(f"Report written to: {output_path}", file=sys.stderr)
    else:
        # render_markdown always ends with \n; use end="" to avoid a double newline.
        print(render_markdown(report), end="")


def _die(message: str) -> None:
    """Print an error message to stderr and exit with code 1."""
    print(f"reviewpilot: error: {message}", file=sys.stderr)
    sys.exit(1)
