"""
Markdown renderer module.

Responsibility: Convert a ReviewReport into a clean, human-readable Markdown
string. This module is purely presentational — no analysis logic here.

Output sections (in order):
    # Title + generated_at
    ## Executive Summary        — totals and detected patterns
    ## Changed Files            — Markdown table (deterministic)
    ## Deterministic Risk Analysis  — per-file signals table (deterministic)
    ## AI-Assisted Regression Hypotheses  — ⚠️ AI-generated
    ## AI-Assisted Test Suggestions       — ⚠️ AI-generated
    ## Human Reviewer Checklist           — ⚠️ AI-generated
    ## Assumptions and Limitations        — AI + fixed MVP note

AI-generated sections are clearly labeled so reviewers know what was
computed vs. what was suggested by the LLM.

Public interface:
    render_markdown(report: ReviewReport) -> str
        Return the full Markdown string for a ReviewReport.

    render_to_file(report: ReviewReport, path: Path) -> None
        Write the Markdown string to a file (thin wrapper).
"""

from __future__ import annotations

from pathlib import Path

from reviewpilot.models import ReviewReport


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_markdown(report: ReviewReport) -> str:
    """Convert a ReviewReport to a Markdown string.

    Output is deterministic for the same input. AI-generated sections are
    clearly labeled with a ⚠️ banner. The string always ends with a newline.

    Args:
        report: The fully assembled ReviewReport to render.

    Returns:
        A Markdown string suitable for stdout, a file, or a PR comment.
    """
    lines: list[str] = []

    _add_title(report, lines)
    _add_executive_summary(report, lines)
    _add_changed_files(report, lines)
    _add_risk_analysis(report, lines)
    _add_regression_hypotheses(report, lines)
    _add_test_suggestions(report, lines)
    _add_reviewer_checklist(report, lines)
    _add_assumptions(report, lines)

    output = "\n".join(lines)
    if not output.endswith("\n"):
        output += "\n"
    return output


def render_to_file(report: ReviewReport, path: Path) -> None:
    """Write the rendered Markdown report to a file.

    Args:
        report: The ReviewReport to render.
        path:   Destination path. Created or overwritten.
    """
    path.write_text(render_markdown(report), encoding="utf-8")


# ---------------------------------------------------------------------------
# Private section builders
# ---------------------------------------------------------------------------


def _add_title(report: ReviewReport, lines: list[str]) -> None:
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append("")
    lines.append("---")
    lines.append("")


def _add_executive_summary(report: ReviewReport, lines: list[str]) -> None:
    ctx = report.context
    patterns = (
        ", ".join(ctx.detected_patterns) if ctx.detected_patterns else "None"
    )

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Files changed:** {ctx.total_files}")
    lines.append(f"- **Lines added:** {ctx.total_additions}")
    lines.append(f"- **Lines removed:** {ctx.total_deletions}")
    lines.append(f"- **Detected risk patterns:** {patterns}")
    lines.append("")


def _add_changed_files(report: ReviewReport, lines: list[str]) -> None:
    lines.append("## Changed Files")
    lines.append("")
    lines.append("| File | Role | Change | +Lines | -Lines | Risk | Score |")
    lines.append("|------|------|--------|-------:|-------:|------|------:|")

    for fs in report.context.file_summaries:
        path = _esc(fs.diff_file.display_path)
        role = fs.role.value.upper()
        change = fs.diff_file.change_type.value.upper()
        risk = fs.risk.level.value.upper()
        lines.append(
            f"| `{path}` | {role} | {change} "
            f"| {fs.diff_file.additions} | {fs.diff_file.deletions} "
            f"| {risk} | {fs.risk.score} |"
        )

    lines.append("")


def _add_risk_analysis(report: ReviewReport, lines: list[str]) -> None:
    lines.append("## Deterministic Risk Analysis")
    lines.append("")
    lines.append(
        "> ✅ This section is computed deterministically — no AI involvement."
    )
    lines.append("")

    for fs in report.context.file_summaries:
        path = _esc(fs.diff_file.display_path)
        level = fs.risk.level.value.upper()

        lines.append(f"### `{path}` — {level} (score: {fs.risk.score})")
        lines.append("")

        if fs.risk.signals:
            lines.append("| Signal | Weight | Reason |")
            lines.append("|--------|-------:|--------|")
            for sig in fs.risk.signals:
                weight_str = (
                    f"+{sig.weight}" if sig.weight >= 0 else str(sig.weight)
                )
                lines.append(
                    f"| {_esc(sig.label)} | {weight_str} | {_esc(sig.reason)} |"
                )
        else:
            lines.append("No risk signals triggered.")

        lines.append("")


def _add_regression_hypotheses(report: ReviewReport, lines: list[str]) -> None:
    lines.append("## AI-Assisted Regression Hypotheses")
    lines.append("")
    lines.append(
        "> ⚠️ **AI-generated suggestions** — treat as hypotheses, not facts."
    )
    lines.append("")

    for item in report.ai_insights.regression_hypotheses:
        lines.append(f"- {item}")

    lines.append("")


def _add_test_suggestions(report: ReviewReport, lines: list[str]) -> None:
    lines.append("## AI-Assisted Test Suggestions")
    lines.append("")
    lines.append(
        "> ⚠️ **AI-generated suggestions** — validate with domain knowledge."
    )
    lines.append("")

    for item in report.ai_insights.test_suggestions:
        lines.append(f"- {item}")

    lines.append("")


def _add_reviewer_checklist(report: ReviewReport, lines: list[str]) -> None:
    lines.append("## Human Reviewer Checklist")
    lines.append("")
    lines.append(
        "> ⚠️ **AI-generated starting point** — use as a prompt for manual review."
    )
    lines.append("")

    for item in report.ai_insights.reviewer_checklist:
        lines.append(f"- [ ] {item}")

    lines.append("")


def _add_assumptions(report: ReviewReport, lines: list[str]) -> None:
    lines.append("## Assumptions and Limitations")
    lines.append("")

    for item in report.ai_insights.assumptions:
        lines.append(f"- {item}")

    lines.append("")
    lines.append(
        "> **Note:** This report uses `MockAIClient` and does not inspect full "
        "repository behaviour, test coverage, or runtime characteristics. "
        "All AI sections are based solely on diff metadata and static keyword matching."
    )
    lines.append("")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Escape pipe characters for safe inclusion in Markdown table cells."""
    return text.replace("|", r"\|")
