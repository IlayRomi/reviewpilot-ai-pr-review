"""
Markdown renderer module.

Responsibility: Convert a ReviewReport into a clean, human-readable Markdown
string. This module is purely presentational — no analysis logic here.

Output sections:
    # PR Review Report          — title + metadata (filename, timestamp)
    ## Summary                  — overall stats (files changed, lines, risk dist.)
    ## Risk Analysis            — per-file risk table with signals (DETERMINISTIC)
    ## Regression Hypotheses    — AI-suggested areas likely to regress (AI-ASSISTED)
    ## Test Suggestions         — AI-suggested tests by type (AI-ASSISTED)
    ## Reviewer Checklist       — AI-generated review checklist (AI-ASSISTED)
    ## Assumptions              — what the AI assumed about the codebase

AI-generated sections are clearly labeled with an ⚠️ banner to maintain
epistemic honesty — reviewers know what was computed versus what was suggested.

Public interface (to be implemented in Commit #8):
    render_report(report: ReviewReport) -> str
        Return the full Markdown string for a ReviewReport.

    render_to_file(report: ReviewReport, path: Path) -> None
        Write the Markdown string to a file.
"""

# Implementation will be added in Commit #8.
