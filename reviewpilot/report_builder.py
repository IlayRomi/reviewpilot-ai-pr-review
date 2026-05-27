"""
Report builder module.

Responsibility: Orchestrate the full analysis pipeline and assemble the
final ReviewReport. This is the main integration point — all other modules
are stateless utilities called from here.

Pipeline:
    1. parser.parse_diff_text(text)       → list[DiffFile]
    2. classifier.classify_file(path)     → FileRole          (per file)
    3. risk_scorer.score_file(...)        → RiskScore         (per file, with all_roles)
    4. Build FileSummary list
    5. Compute AnalysisContext            (no raw diff text passed to AI)
    6. ai_client.generate_insights(ctx)  → AIInsights
    7. Assemble ReviewReport

Design constraints:
    - Raw diff text is never forwarded to the AI client.
    - The AI client receives only the structured AnalysisContext.
    - all_roles (all FileRoles in this diff) is passed to score_file so the
      NO_TEST_COVERAGE signal fires correctly when no test file is present.
    - MockAIClient is used by default so the tool works offline with no config.

Public interface:
    build_report_from_text(diff_text, ai_client=None, title=...) -> ReviewReport
    build_report_from_file(path, ai_client=None, title=...)       -> ReviewReport
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reviewpilot.ai_client import AIClient
from reviewpilot.ai_client import MockAIClient as _DefaultAIClient
from reviewpilot.classifier import classify_file
from reviewpilot.models import AnalysisContext, FileSummary, ReviewReport
from reviewpilot.parser import parse_diff_text
from reviewpilot.risk_scorer import score_file

_DEFAULT_TITLE = "ReviewPilot PR Review Report"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_report_from_text(
    diff_text: str,
    ai_client: AIClient | None = None,
    title: str = _DEFAULT_TITLE,
) -> ReviewReport:
    """Run the full pipeline on diff text and return a ReviewReport.

    Args:
        diff_text:  Raw unified diff text (output of `git diff`).
        ai_client:  AI client implementing the AIClient Protocol.
                    Defaults to MockAIClient when None.
        title:      Human-readable report title.

    Returns:
        A ReviewReport with deterministic analysis + AI-generated insights.

    Raises:
        ValueError: Propagated from the parser if diff_text is empty or
                    contains no parseable files.
    """
    if ai_client is None:
        ai_client = _DefaultAIClient()

    # ── Step 1: Parse ────────────────────────────────────────────────────
    diff_files = parse_diff_text(diff_text)

    # ── Step 2: Classify ─────────────────────────────────────────────────
    roles = [classify_file(df.display_path) for df in diff_files]

    # ── Step 3: Score (pass all_roles so NO_TEST_COVERAGE works) ─────────
    file_summaries: list[FileSummary] = [
        FileSummary(
            diff_file=df,
            role=role,
            risk=score_file(df, role, all_roles=roles),
        )
        for df, role in zip(diff_files, roles)
    ]

    # ── Step 4: Build AnalysisContext (no raw diff text) ─────────────────
    context = AnalysisContext(
        file_summaries=file_summaries,
        total_files=len(file_summaries),
        total_additions=sum(df.additions for df in diff_files),
        total_deletions=sum(df.deletions for df in diff_files),
        detected_patterns=_extract_detected_patterns(file_summaries),
    )

    # ── Step 5: Generate AI insights ─────────────────────────────────────
    ai_insights = ai_client.generate_insights(context)

    # ── Step 6: Assemble report ───────────────────────────────────────────
    return ReviewReport(
        title=title,
        generated_at=datetime.now(timezone.utc).isoformat(),
        context=context,
        ai_insights=ai_insights,
    )


def build_report_from_file(
    path: Path,
    ai_client: AIClient | None = None,
    title: str = _DEFAULT_TITLE,
) -> ReviewReport:
    """Read a .diff file from disk and run the full pipeline.

    A thin wrapper around build_report_from_text that handles file I/O.

    Args:
        path:      Path to a unified diff file on disk.
        ai_client: AI client implementing the AIClient Protocol.
                   Defaults to MockAIClient when None.
        title:     Human-readable report title.

    Returns:
        A ReviewReport with deterministic analysis + AI-generated insights.

    Raises:
        ValueError: If the file cannot be read, is empty, or has no parseable files.
    """
    try:
        diff_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read diff file '{path}': {exc}") from exc
    return build_report_from_text(diff_text, ai_client=ai_client, title=title)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_detected_patterns(file_summaries: list[FileSummary]) -> list[str]:
    """Collect unique risk signal labels across all file summaries.

    Returns a sorted list so the output is deterministic and easy to test.
    This list becomes part of AnalysisContext — it tells the AI layer which
    risk categories were triggered without exposing raw diff content.
    """
    seen: set[str] = set()
    for fs in file_summaries:
        for signal in fs.risk.signals:
            seen.add(signal.label)
    return sorted(seen)
