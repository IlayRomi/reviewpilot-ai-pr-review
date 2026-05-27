"""
CLI entry point for ReviewPilot.

Usage:
    python -m reviewpilot <diff_file> [--output <path>] [--mock-ai]

Arguments:
    diff_file       Path to a unified diff file (.diff) to analyze.

Options:
    --output PATH   Write the Markdown report to a file instead of stdout.
    --mock-ai       Force use of MockAIClient even if a real client is configured.
                    (Implicit in MVP — always uses mock.)

Uses argparse from the Python standard library only. No third-party CLI
frameworks are required.

Public interface (to be implemented in Commit #9):
    main() -> None
        Parse arguments, run the pipeline, write or print the report.
        Called by the `reviewpilot` console script entry point.

    Entry point also supports `python -m reviewpilot` via __main__.py.
"""

# Implementation will be added in Commit #9.


def main() -> None:
    """Placeholder entry point — implemented in Commit #9."""
    print("ReviewPilot scaffold — implementation coming in Commit #9.")
