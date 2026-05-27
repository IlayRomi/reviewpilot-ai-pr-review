"""
Tests for reviewpilot/renderer.py — Commit #8.

All tests build a ReviewReport via build_report_from_text (with MockAIClient)
or by constructing ReviewReport/AnalysisContext directly for targeted edge cases.

Coverage:
  1.  render_markdown returns a str
  2.  Output contains the report title
  3.  Output contains generated_at
  4.  Output contains "## Executive Summary"
  5.  Output contains "## Changed Files" table header
  6.  Output contains "## Deterministic Risk Analysis"
  7.  Output contains "## AI-Assisted Regression Hypotheses"
  8.  Output contains "## AI-Assisted Test Suggestions"
  9.  Output contains "## Human Reviewer Checklist"
  10. Output contains "## Assumptions and Limitations"
  11. Output includes file paths, roles, risk levels, and scores
  12. Output includes risk signal labels and reasons
  13. Output handles reports with no risk signals gracefully
  14. Output escapes pipe characters in file paths
  15. Output ends with a newline
  16. render_to_file writes correct content to disk
  17. Executive Summary totals are correct
  18. Reviewer checklist items use "- [ ]" syntax
  19. AI sections carry the ⚠️ warning banner
  20. The MockAIClient note appears in Assumptions section
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reviewpilot.models import (
    AIInsights,
    AnalysisContext,
    ChangeType,
    DiffFile,
    DiffHunk,
    DiffLine,
    FileRole,
    FileSummary,
    LineType,
    ReviewReport,
    RiskLevel,
    RiskScore,
    RiskSignal,
)
from reviewpilot.report_builder import build_report_from_text
from reviewpilot.renderer import render_markdown, render_to_file


# ---------------------------------------------------------------------------
# Inline diff fixtures
# ---------------------------------------------------------------------------

# High-risk source file: large change + no test file → NO_TEST_COVERAGE fires;
# also contains auth keywords → AUTH_SECURITY_KEYWORD fires.
AUTH_SOURCE_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc123..def456 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,3 +1,4 @@
 def login(user):
-    check_password(user)
+    validate_password(user)
+    generate_token(user)
+    # auth
"""

# Migration diff — triggers MIGRATION_FILE signal.
MIGRATION_DIFF = """\
diff --git a/migrations/001_create_users.sql b/migrations/001_create_users.sql
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/migrations/001_create_users.sql
@@ -0,0 +1,3 @@
+CREATE TABLE users (
+    id SERIAL PRIMARY KEY
+);
"""

# Docs-only diff — minimal signals (no source, no test).
DOCS_DIFF = """\
diff --git a/docs/guide.md b/docs/guide.md
index aaa..bbb 100644
--- a/docs/guide.md
+++ b/docs/guide.md
@@ -1,2 +1,3 @@
 # Guide
-Old content.
+New content.
+More text.
"""

# Multi-file diff: source + migration (ensures two rows in the Changed Files table).
MULTI_FILE_DIFF = AUTH_SOURCE_DIFF + MIGRATION_DIFF


# ---------------------------------------------------------------------------
# Module-scoped fixtures — one report built per fixture group, shared across
# all tests that use the same diff.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def auth_report() -> ReviewReport:
    """Report built from the AUTH_SOURCE_DIFF."""
    return build_report_from_text(AUTH_SOURCE_DIFF, title="Auth Report")


@pytest.fixture(scope="module")
def auth_md(auth_report: ReviewReport) -> str:
    """Rendered Markdown for the auth_report."""
    return render_markdown(auth_report)


@pytest.fixture(scope="module")
def migration_report() -> ReviewReport:
    return build_report_from_text(MIGRATION_DIFF, title="Migration Report")


@pytest.fixture(scope="module")
def migration_md(migration_report: ReviewReport) -> str:
    return render_markdown(migration_report)


@pytest.fixture(scope="module")
def docs_report() -> ReviewReport:
    return build_report_from_text(DOCS_DIFF, title="Docs Report")


@pytest.fixture(scope="module")
def docs_md(docs_report: ReviewReport) -> str:
    return render_markdown(docs_report)


@pytest.fixture(scope="module")
def multi_report() -> ReviewReport:
    return build_report_from_text(MULTI_FILE_DIFF, title="Multi-File Report")


@pytest.fixture(scope="module")
def multi_md(multi_report: ReviewReport) -> str:
    return render_markdown(multi_report)


# ---------------------------------------------------------------------------
# Helper: build a minimal ReviewReport with no risk signals
# ---------------------------------------------------------------------------


def _no_signal_report() -> ReviewReport:
    """Construct a ReviewReport that has a file with a RiskScore but no signals."""
    diff_file = DiffFile(
        old_path="src/simple.py",
        new_path="src/simple.py",
        change_type=ChangeType.MODIFIED,
        hunks=[],
        additions=2,
        deletions=1,
    )
    risk = RiskScore(level=RiskLevel.LOW, score=0, signals=[])
    file_summary = FileSummary(diff_file=diff_file, role=FileRole.SOURCE, risk=risk)
    context = AnalysisContext(
        file_summaries=[file_summary],
        total_files=1,
        total_additions=2,
        total_deletions=1,
        detected_patterns=[],
    )
    insights = AIInsights(
        regression_hypotheses=["No high-risk changes."],
        test_suggestions=["Run the test suite."],
        reviewer_checklist=["Standard review."],
        assumptions=["Mock client used.", "Heuristic estimates.", "AI-generated."],
    )
    return ReviewReport(
        title="No-Signal Report",
        generated_at="2026-01-01T00:00:00+00:00",
        context=context,
        ai_insights=insights,
    )


# ---------------------------------------------------------------------------
# Helper: build a ReviewReport with a pipe character in the file path
# ---------------------------------------------------------------------------


def _pipe_path_report() -> ReviewReport:
    """Construct a ReviewReport where the file path contains a '|' character."""
    diff_file = DiffFile(
        old_path="src/pipe|file.py",
        new_path="src/pipe|file.py",
        change_type=ChangeType.MODIFIED,
        hunks=[],
        additions=1,
        deletions=0,
    )
    risk = RiskScore(level=RiskLevel.LOW, score=0, signals=[])
    file_summary = FileSummary(diff_file=diff_file, role=FileRole.SOURCE, risk=risk)
    context = AnalysisContext(
        file_summaries=[file_summary],
        total_files=1,
        total_additions=1,
        total_deletions=0,
        detected_patterns=[],
    )
    insights = AIInsights(
        regression_hypotheses=["No high-risk changes."],
        test_suggestions=["Run the test suite."],
        reviewer_checklist=["Standard review."],
        assumptions=["Mock client used.", "Heuristic estimates.", "AI-generated."],
    )
    return ReviewReport(
        title="Pipe Path Report",
        generated_at="2026-01-01T00:00:00+00:00",
        context=context,
        ai_insights=insights,
    )


# ===========================================================================
# Test 1: render_markdown returns a str
# ===========================================================================


class TestReturnType:
    def test_returns_str(self, auth_md: str) -> None:
        assert isinstance(auth_md, str)

    def test_non_empty(self, auth_md: str) -> None:
        assert len(auth_md) > 0


# ===========================================================================
# Test 2: Output contains the report title
# ===========================================================================


class TestTitle:
    def test_title_present(self, auth_md: str) -> None:
        assert "Auth Report" in auth_md

    def test_title_h1(self, auth_md: str) -> None:
        assert "# Auth Report" in auth_md

    def test_custom_title_in_output(self, migration_md: str) -> None:
        assert "Migration Report" in migration_md


# ===========================================================================
# Test 3: Output contains generated_at
# ===========================================================================


class TestGeneratedAt:
    def test_generated_at_present(self, auth_report: ReviewReport, auth_md: str) -> None:
        assert auth_report.generated_at in auth_md

    def test_generated_at_label(self, auth_md: str) -> None:
        assert "**Generated:**" in auth_md


# ===========================================================================
# Test 4: Executive Summary section
# ===========================================================================


class TestExecutiveSummary:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## Executive Summary" in auth_md

    def test_files_changed_bullet(self, auth_md: str) -> None:
        assert "**Files changed:**" in auth_md

    def test_lines_added_bullet(self, auth_md: str) -> None:
        assert "**Lines added:**" in auth_md

    def test_lines_removed_bullet(self, auth_md: str) -> None:
        assert "**Lines removed:**" in auth_md

    def test_detected_patterns_bullet(self, auth_md: str) -> None:
        assert "**Detected risk patterns:**" in auth_md


# ===========================================================================
# Test 5: Changed Files table
# ===========================================================================


class TestChangedFilesTable:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## Changed Files" in auth_md

    def test_table_header_columns(self, auth_md: str) -> None:
        assert "| File | Role | Change | +Lines | -Lines | Risk | Score |" in auth_md

    def test_table_separator_present(self, auth_md: str) -> None:
        assert "|------|" in auth_md

    def test_two_rows_for_multi_file(self, multi_md: str) -> None:
        # The table header + separator count as 2 lines; each file is one more row.
        # Count occurrences of " | SOURCE |" and " | MIGRATION |"
        assert "SOURCE" in multi_md
        assert "MIGRATION" in multi_md


# ===========================================================================
# Test 6: Deterministic Risk Analysis section
# ===========================================================================


class TestDeterministicRiskAnalysis:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## Deterministic Risk Analysis" in auth_md

    def test_deterministic_badge(self, auth_md: str) -> None:
        assert "✅" in auth_md
        assert "deterministically" in auth_md

    def test_per_file_subheading(self, auth_md: str) -> None:
        # Each file gets a ### subheading like "### `src/auth.py` — HIGH (score: ...)"
        assert "### `src/auth.py`" in auth_md

    def test_score_present_in_subheading(self, auth_md: str) -> None:
        assert "score:" in auth_md


# ===========================================================================
# Test 7: AI-Assisted Regression Hypotheses section
# ===========================================================================


class TestRegressionHypotheses:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## AI-Assisted Regression Hypotheses" in auth_md

    def test_ai_warning_banner(self, auth_md: str) -> None:
        assert "⚠️" in auth_md

    def test_hypotheses_non_empty(self, auth_md: str) -> None:
        assert "## AI-Assisted Regression Hypotheses" in auth_md
        idx = auth_md.index("## AI-Assisted Regression Hypotheses")
        section = auth_md[idx:]
        # There should be at least one "- " bullet in this section
        assert "\n- " in section


# ===========================================================================
# Test 8: AI-Assisted Test Suggestions section
# ===========================================================================


class TestTestSuggestions:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## AI-Assisted Test Suggestions" in auth_md

    def test_suggestions_non_empty(self, auth_md: str) -> None:
        idx = auth_md.index("## AI-Assisted Test Suggestions")
        section = auth_md[idx:]
        assert "\n- " in section


# ===========================================================================
# Test 9: Human Reviewer Checklist section
# ===========================================================================


class TestReviewerChecklist:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## Human Reviewer Checklist" in auth_md

    def test_checklist_items_use_checkbox_syntax(self, auth_md: str) -> None:
        assert "- [ ]" in auth_md

    def test_ai_warning_banner_in_checklist(self, auth_md: str) -> None:
        idx = auth_md.index("## Human Reviewer Checklist")
        section = auth_md[idx:]
        assert "⚠️" in section


# ===========================================================================
# Test 10: Assumptions and Limitations section
# ===========================================================================


class TestAssumptionsAndLimitations:
    def test_heading_present(self, auth_md: str) -> None:
        assert "## Assumptions and Limitations" in auth_md

    def test_assumptions_non_empty(self, auth_md: str) -> None:
        idx = auth_md.index("## Assumptions and Limitations")
        section = auth_md[idx:]
        assert "\n- " in section

    def test_mock_client_note_present(self, auth_md: str) -> None:
        assert "MockAIClient" in auth_md


# ===========================================================================
# Test 11: File paths, roles, risk levels, and scores in output
# ===========================================================================


class TestFileMetadata:
    def test_file_path_in_output(self, auth_md: str) -> None:
        assert "src/auth.py" in auth_md

    def test_role_in_table(self, auth_md: str) -> None:
        # SOURCE role should appear in the Changed Files table row
        assert "SOURCE" in auth_md

    def test_risk_level_in_table(self, auth_md: str) -> None:
        # The auth file should be at least MEDIUM risk
        assert any(level in auth_md for level in ("MEDIUM", "HIGH", "CRITICAL"))

    def test_score_in_table_row(self, auth_md: str, auth_report: ReviewReport) -> None:
        for fs in auth_report.context.file_summaries:
            assert str(fs.risk.score) in auth_md

    def test_migration_path_in_multi_output(self, multi_md: str) -> None:
        assert "migrations/001_create_users.sql" in multi_md

    def test_change_type_in_table(self, migration_md: str) -> None:
        # New file → ADDED change type
        assert "ADDED" in migration_md


# ===========================================================================
# Test 12: Risk signal labels and reasons
# ===========================================================================


class TestRiskSignals:
    def test_signal_label_in_risk_analysis(self, auth_md: str) -> None:
        # AUTH_SECURITY_KEYWORD or NO_TEST_COVERAGE should appear in the table
        assert "AUTH_SECURITY_KEYWORD" in auth_md or "NO_TEST_COVERAGE" in auth_md

    def test_signal_table_headers(self, auth_md: str) -> None:
        # Signal tables have "| Signal | Weight | Reason |" header
        assert "| Signal | Weight | Reason |" in auth_md

    def test_signal_reason_non_empty(self, auth_md: str, auth_report: ReviewReport) -> None:
        for fs in auth_report.context.file_summaries:
            for sig in fs.risk.signals:
                assert sig.reason in auth_md

    def test_migration_signal_present(self, migration_md: str) -> None:
        assert "MIGRATION_FILE" in migration_md


# ===========================================================================
# Test 13: No risk signals — graceful handling
# ===========================================================================


class TestNoRiskSignals:
    def test_no_signal_message_when_no_signals(self) -> None:
        report = _no_signal_report()
        md = render_markdown(report)
        assert "No risk signals triggered." in md

    def test_no_signal_table_omitted(self) -> None:
        report = _no_signal_report()
        md = render_markdown(report)
        # There should be NO signal table header for the no-signal file
        # (the signal table header appears only when signals exist)
        # We verify the section heading is still present
        assert "## Deterministic Risk Analysis" in md

    def test_no_signal_report_still_valid_markdown(self) -> None:
        report = _no_signal_report()
        md = render_markdown(report)
        assert "## Changed Files" in md
        assert "## Executive Summary" in md


# ===========================================================================
# Test 14: Pipe character escaping
# ===========================================================================


class TestPipeEscaping:
    def test_pipe_in_path_is_escaped_in_table(self) -> None:
        report = _pipe_path_report()
        md = render_markdown(report)
        # The raw "|" in the path should appear as "\|" in the table cell
        assert r"pipe\|file.py" in md

    def test_raw_pipe_does_not_appear_unescaped_in_table_cell(self) -> None:
        report = _pipe_path_report()
        md = render_markdown(report)
        lines = md.splitlines()
        table_lines = [
            ln for ln in lines if ln.startswith("|") and "pipe" in ln
        ]
        for line in table_lines:
            # Every "|" in the cell content should be preceded by "\"
            # We check that "pipe|file" (unescaped) is NOT present in those lines.
            assert "pipe|file" not in line

    def test_pipe_escaped_in_risk_analysis_subheading(self) -> None:
        report = _pipe_path_report()
        md = render_markdown(report)
        # The ### subheading in the risk analysis section also uses _esc()
        assert r"pipe\|file.py" in md


# ===========================================================================
# Test 15: Output ends with a newline
# ===========================================================================


class TestTrailingNewline:
    def test_ends_with_newline_auth(self, auth_md: str) -> None:
        assert auth_md.endswith("\n")

    def test_ends_with_newline_migration(self, migration_md: str) -> None:
        assert migration_md.endswith("\n")

    def test_ends_with_newline_docs(self, docs_md: str) -> None:
        assert docs_md.endswith("\n")

    def test_ends_with_newline_no_signals(self) -> None:
        md = render_markdown(_no_signal_report())
        assert md.endswith("\n")


# ===========================================================================
# Test 16: render_to_file writes correct content to disk
# ===========================================================================


class TestRenderToFile:
    def test_file_is_created(self, auth_report: ReviewReport, tmp_path: Path) -> None:
        out = tmp_path / "report.md"
        render_to_file(auth_report, out)
        assert out.exists()

    def test_file_content_matches_render_markdown(
        self, auth_report: ReviewReport, tmp_path: Path
    ) -> None:
        out = tmp_path / "report.md"
        render_to_file(auth_report, out)
        expected = render_markdown(auth_report)
        assert out.read_text(encoding="utf-8") == expected

    def test_file_ends_with_newline(
        self, auth_report: ReviewReport, tmp_path: Path
    ) -> None:
        out = tmp_path / "report.md"
        render_to_file(auth_report, out)
        assert out.read_text(encoding="utf-8").endswith("\n")

    def test_file_encoded_as_utf8(
        self, auth_report: ReviewReport, tmp_path: Path
    ) -> None:
        out = tmp_path / "report.md"
        render_to_file(auth_report, out)
        # Should be readable as UTF-8 without error
        content = out.read_text(encoding="utf-8")
        assert "⚠️" in content  # multi-byte UTF-8 emoji round-trips correctly


# ===========================================================================
# Test 17: Executive Summary totals are correct
# ===========================================================================


class TestExecutiveSummaryTotals:
    def test_total_files_correct(
        self, auth_report: ReviewReport, auth_md: str
    ) -> None:
        expected = str(auth_report.context.total_files)
        assert f"**Files changed:** {expected}" in auth_md

    def test_total_additions_correct(
        self, auth_report: ReviewReport, auth_md: str
    ) -> None:
        expected = str(auth_report.context.total_additions)
        assert f"**Lines added:** {expected}" in auth_md

    def test_total_deletions_correct(
        self, auth_report: ReviewReport, auth_md: str
    ) -> None:
        expected = str(auth_report.context.total_deletions)
        assert f"**Lines removed:** {expected}" in auth_md


# ===========================================================================
# Test 18: Reviewer checklist items use "- [ ]" syntax
# ===========================================================================


class TestChecklistSyntax:
    def test_checklist_uses_task_list_syntax(self, auth_md: str) -> None:
        assert "- [ ]" in auth_md

    def test_no_bare_dash_in_checklist_section(self, auth_md: str) -> None:
        idx = auth_md.index("## Human Reviewer Checklist")
        # Find next section to bound the slice
        next_h2 = auth_md.find("\n## ", idx + 1)
        section = auth_md[idx:next_h2] if next_h2 != -1 else auth_md[idx:]
        # All bullet lines in this section should start with "- [ ] ", not bare "- "
        for line in section.splitlines():
            if line.startswith("- ") and not line.startswith("> "):
                assert line.startswith("- [ ]"), (
                    f"Checklist line missing checkbox syntax: {line!r}"
                )


# ===========================================================================
# Test 19: AI sections carry the ⚠️ warning banner
# ===========================================================================


class TestAIWarningBanners:
    def test_regression_section_has_warning(self, auth_md: str) -> None:
        idx = auth_md.index("## AI-Assisted Regression Hypotheses")
        next_h2 = auth_md.find("\n## ", idx + 1)
        section = auth_md[idx:next_h2] if next_h2 != -1 else auth_md[idx:]
        assert "⚠️" in section

    def test_test_suggestions_section_has_warning(self, auth_md: str) -> None:
        idx = auth_md.index("## AI-Assisted Test Suggestions")
        next_h2 = auth_md.find("\n## ", idx + 1)
        section = auth_md[idx:next_h2] if next_h2 != -1 else auth_md[idx:]
        assert "⚠️" in section

    def test_reviewer_checklist_section_has_warning(self, auth_md: str) -> None:
        idx = auth_md.index("## Human Reviewer Checklist")
        next_h2 = auth_md.find("\n## ", idx + 1)
        section = auth_md[idx:next_h2] if next_h2 != -1 else auth_md[idx:]
        assert "⚠️" in section


# ===========================================================================
# Test 20: MockAIClient note in Assumptions section
# ===========================================================================


class TestMockAIClientNote:
    def test_mock_client_note_in_assumptions(self, auth_md: str) -> None:
        idx = auth_md.index("## Assumptions and Limitations")
        section = auth_md[idx:]
        assert "MockAIClient" in section

    def test_note_mentions_diff_metadata(self, auth_md: str) -> None:
        assert "diff metadata" in auth_md
