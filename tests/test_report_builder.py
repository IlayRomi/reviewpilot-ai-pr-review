"""
Tests for reviewpilot/report_builder.py — Commit #7.

All tests use inline diff fixtures. No real API calls; MockAIClient is used
throughout (either explicitly or via the default argument).

Coverage:
  1.  build_report_from_text returns a ReviewReport
  2.  Uses MockAIClient by default (no ai_client argument)
  3.  Correctly computes total_files
  4.  Correctly computes total_additions and total_deletions
  5.  Creates one FileSummary per changed file
  6.  Classifies files correctly (SOURCE, TEST, MIGRATION, CONFIG)
  7.  Scores files correctly (MIGRATION_FILE signal for migration files)
  8.  Passes all_roles → SOURCE without test triggers NO_TEST_COVERAGE
  9.  SOURCE with test file → NO_TEST_COVERAGE does NOT fire
  10. detected_patterns contains the triggered signal labels
  11. AIInsights are populated (non-empty lists)
  12. build_report_from_file works with a temporary .diff file
  13. Empty diff text raises ValueError
  14. generated_at is a non-empty ISO 8601 string
  15. Custom title is respected
  16. A custom AIClient can be injected (replaces mock)
"""

from pathlib import Path

import pytest

from reviewpilot.ai_client import AIClient, MockAIClient
from reviewpilot.models import AIInsights, AnalysisContext, FileRole, ReviewReport
from reviewpilot.report_builder import build_report_from_file, build_report_from_text


# ---------------------------------------------------------------------------
# Inline diff fixtures
# ---------------------------------------------------------------------------

# One modified Python source file — no test file in diff.
SIMPLE_SOURCE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index abc123..def456 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 def greet():
-    return "hello"
+    return "hello, world"
+    # updated
"""

# Source file + test file in same diff.
SOURCE_AND_TEST_DIFF = """\
diff --git a/src/app.py b/src/app.py
index abc123..def456 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 def greet():
-    return "hello"
+    return "hello, world"
+    # updated
diff --git a/tests/test_app.py b/tests/test_app.py
index 111111..222222 100644
--- a/tests/test_app.py
+++ b/tests/test_app.py
@@ -1,2 +1,2 @@
 def test_greet():
-    assert greet() == "hello"
+    assert greet() == "hello, world"
"""

# New database migration file.
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

# Source file containing auth/security keywords.
AUTH_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc123..def456 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,3 @@
 def login(user):
-    check_password(user)
+    validate_password(user)
+    generate_token(user)
"""

# Two files: source + migration (for multi-file tests).
MULTI_FILE_DIFF = SIMPLE_SOURCE_DIFF + MIGRATION_DIFF

# Configuration file change.
CONFIG_DIFF = """\
diff --git a/pyproject.toml b/pyproject.toml
index aaa..bbb 100644
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -1,2 +1,3 @@
 [project]
-version = "0.1.0"
+version = "0.2.0"
+description = "updated"
"""


# ---------------------------------------------------------------------------
# Helper: spy AI client for test 16
# ---------------------------------------------------------------------------

class _RecordingAIClient:
    """Minimal AIClient that records how many times it was called."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_context: AnalysisContext | None = None

    def generate_insights(self, context: AnalysisContext) -> AIInsights:
        self.call_count += 1
        self.last_context = context
        return AIInsights(
            regression_hypotheses=["spy hypothesis"],
            test_suggestions=["spy test"],
            reviewer_checklist=["spy checklist"],
            assumptions=["spy assumption"],
        )


# ---------------------------------------------------------------------------
# Test 1: Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_review_report(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert isinstance(report, ReviewReport)

    def test_context_is_analysis_context(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert isinstance(report.context, AnalysisContext)

    def test_ai_insights_is_correct_type(self) -> None:
        from reviewpilot.models import AIInsights
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert isinstance(report.ai_insights, AIInsights)


# ---------------------------------------------------------------------------
# Test 2: Uses MockAIClient by default
# ---------------------------------------------------------------------------


class TestDefaultAIClient:
    def test_no_ai_client_arg_does_not_raise(self) -> None:
        """build_report_from_text(diff) should work with no ai_client argument."""
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert report is not None

    def test_assumptions_contain_mock_indicator(self) -> None:
        """MockAIClient always includes 'mock' in its assumptions."""
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        combined = " ".join(report.ai_insights.assumptions).lower()
        assert "mock" in combined


# ---------------------------------------------------------------------------
# Test 3: total_files
# ---------------------------------------------------------------------------


class TestTotalFiles:
    def test_single_file_diff(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert report.context.total_files == 1

    def test_two_file_diff(self) -> None:
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        assert report.context.total_files == 2

    def test_migration_diff_has_one_file(self) -> None:
        report = build_report_from_text(MIGRATION_DIFF)
        assert report.context.total_files == 1

    def test_multi_file_diff(self) -> None:
        report = build_report_from_text(MULTI_FILE_DIFF)
        assert report.context.total_files == 2


# ---------------------------------------------------------------------------
# Test 4: total_additions and total_deletions
# ---------------------------------------------------------------------------


class TestLineCounts:
    def test_simple_source_additions(self) -> None:
        # SIMPLE_SOURCE_DIFF: 2 added lines
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert report.context.total_additions == 2

    def test_simple_source_deletions(self) -> None:
        # SIMPLE_SOURCE_DIFF: 1 removed line
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert report.context.total_deletions == 1

    def test_source_and_test_additions(self) -> None:
        # src/app.py: +2, tests/test_app.py: +1  → total 3
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        assert report.context.total_additions == 3

    def test_source_and_test_deletions(self) -> None:
        # src/app.py: -1, tests/test_app.py: -1  → total 2
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        assert report.context.total_deletions == 2

    def test_migration_only_additions(self) -> None:
        # MIGRATION_DIFF: 3 added lines, 0 removed
        report = build_report_from_text(MIGRATION_DIFF)
        assert report.context.total_additions == 3
        assert report.context.total_deletions == 0

    def test_multi_file_totals(self) -> None:
        # src/app.py (+2,-1) + migrations (+3,-0) = (+5,-1)
        report = build_report_from_text(MULTI_FILE_DIFF)
        assert report.context.total_additions == 5
        assert report.context.total_deletions == 1


# ---------------------------------------------------------------------------
# Test 5: One FileSummary per file
# ---------------------------------------------------------------------------


class TestFileSummaries:
    def test_single_diff_has_one_summary(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert len(report.context.file_summaries) == 1

    def test_two_file_diff_has_two_summaries(self) -> None:
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        assert len(report.context.file_summaries) == 2

    def test_summaries_count_matches_total_files(self) -> None:
        report = build_report_from_text(MULTI_FILE_DIFF)
        assert len(report.context.file_summaries) == report.context.total_files


# ---------------------------------------------------------------------------
# Test 6: File classification
# ---------------------------------------------------------------------------


class TestClassification:
    def test_python_source_file_is_source(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert report.context.file_summaries[0].role is FileRole.SOURCE

    def test_test_file_is_test(self) -> None:
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        roles = {fs.role for fs in report.context.file_summaries}
        assert FileRole.TEST in roles

    def test_migration_file_is_migration(self) -> None:
        report = build_report_from_text(MIGRATION_DIFF)
        assert report.context.file_summaries[0].role is FileRole.MIGRATION

    def test_config_file_is_config(self) -> None:
        report = build_report_from_text(CONFIG_DIFF)
        assert report.context.file_summaries[0].role is FileRole.CONFIG

    def test_multi_file_diff_has_source_and_migration(self) -> None:
        report = build_report_from_text(MULTI_FILE_DIFF)
        roles = {fs.role for fs in report.context.file_summaries}
        assert FileRole.SOURCE in roles
        assert FileRole.MIGRATION in roles


# ---------------------------------------------------------------------------
# Test 7: Risk scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_migration_file_has_migration_signal(self) -> None:
        report = build_report_from_text(MIGRATION_DIFF)
        fs = report.context.file_summaries[0]
        signal_labels = {s.label for s in fs.risk.signals}
        assert "MIGRATION_FILE" in signal_labels

    def test_auth_diff_has_auth_signal(self) -> None:
        report = build_report_from_text(AUTH_DIFF)
        fs = report.context.file_summaries[0]
        signal_labels = {s.label for s in fs.risk.signals}
        assert "AUTH_SECURITY_KEYWORD" in signal_labels

    def test_config_diff_has_config_signal(self) -> None:
        report = build_report_from_text(CONFIG_DIFF)
        fs = report.context.file_summaries[0]
        signal_labels = {s.label for s in fs.risk.signals}
        assert "CONFIG_CHANGE" in signal_labels

    def test_risk_score_is_non_negative(self) -> None:
        for diff in (SIMPLE_SOURCE_DIFF, MIGRATION_DIFF, AUTH_DIFF, CONFIG_DIFF):
            report = build_report_from_text(diff)
            for fs in report.context.file_summaries:
                assert fs.risk.score >= 0, f"Negative score for {fs.diff_file.display_path}"


# ---------------------------------------------------------------------------
# Test 8: all_roles propagation → NO_TEST_COVERAGE fires
# ---------------------------------------------------------------------------


class TestNoTestCoverageSignal:
    def test_source_without_test_triggers_no_test_coverage(self) -> None:
        """SIMPLE_SOURCE_DIFF has only src/app.py — no test file."""
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        source_fs = next(
            fs for fs in report.context.file_summaries
            if fs.role is FileRole.SOURCE
        )
        signal_labels = {s.label for s in source_fs.risk.signals}
        assert "NO_TEST_COVERAGE" in signal_labels

    def test_detected_patterns_includes_no_test_coverage(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert "NO_TEST_COVERAGE" in report.context.detected_patterns


# ---------------------------------------------------------------------------
# Test 9: NO_TEST_COVERAGE absent when test file is present
# ---------------------------------------------------------------------------


class TestNoTestCoverageAbsent:
    def test_source_with_test_does_not_trigger_no_test_coverage(self) -> None:
        """SOURCE_AND_TEST_DIFF includes both src/app.py and tests/test_app.py."""
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        source_fs = next(
            fs for fs in report.context.file_summaries
            if fs.role is FileRole.SOURCE
        )
        signal_labels = {s.label for s in source_fs.risk.signals}
        assert "NO_TEST_COVERAGE" not in signal_labels

    def test_no_test_coverage_absent_from_detected_patterns(self) -> None:
        report = build_report_from_text(SOURCE_AND_TEST_DIFF)
        assert "NO_TEST_COVERAGE" not in report.context.detected_patterns


# ---------------------------------------------------------------------------
# Test 10: detected_patterns
# ---------------------------------------------------------------------------


class TestDetectedPatterns:
    def test_detected_patterns_is_a_list(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert isinstance(report.context.detected_patterns, list)

    def test_detected_patterns_are_strings(self) -> None:
        report = build_report_from_text(MIGRATION_DIFF)
        assert all(isinstance(p, str) for p in report.context.detected_patterns)

    def test_migration_diff_has_migration_pattern(self) -> None:
        report = build_report_from_text(MIGRATION_DIFF)
        assert "MIGRATION_FILE" in report.context.detected_patterns

    def test_auth_diff_has_auth_pattern(self) -> None:
        report = build_report_from_text(AUTH_DIFF)
        assert "AUTH_SECURITY_KEYWORD" in report.context.detected_patterns

    def test_detected_patterns_are_sorted(self) -> None:
        """Patterns should be sorted alphabetically for determinism."""
        report = build_report_from_text(AUTH_DIFF)
        patterns = report.context.detected_patterns
        assert patterns == sorted(patterns)

    def test_no_duplicate_patterns(self) -> None:
        """Each signal label appears at most once in detected_patterns."""
        report = build_report_from_text(MULTI_FILE_DIFF)
        assert len(report.context.detected_patterns) == len(set(report.context.detected_patterns))


# ---------------------------------------------------------------------------
# Test 11: AIInsights populated
# ---------------------------------------------------------------------------


class TestAIInsightsPopulated:
    def test_regression_hypotheses_non_empty(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert len(report.ai_insights.regression_hypotheses) >= 1

    def test_test_suggestions_non_empty(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert len(report.ai_insights.test_suggestions) >= 1

    def test_reviewer_checklist_non_empty(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert len(report.ai_insights.reviewer_checklist) >= 1

    def test_assumptions_non_empty(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert len(report.ai_insights.assumptions) >= 1

    def test_insights_are_strings(self) -> None:
        report = build_report_from_text(MIGRATION_DIFF)
        insights = report.ai_insights
        for field in (
            insights.regression_hypotheses,
            insights.test_suggestions,
            insights.reviewer_checklist,
            insights.assumptions,
        ):
            assert all(isinstance(item, str) for item in field)


# ---------------------------------------------------------------------------
# Test 12: build_report_from_file
# ---------------------------------------------------------------------------


class TestBuildFromFile:
    def test_from_file_returns_review_report(self, tmp_path: Path) -> None:
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(SIMPLE_SOURCE_DIFF, encoding="utf-8")
        report = build_report_from_file(diff_file)
        assert isinstance(report, ReviewReport)

    def test_from_file_total_files(self, tmp_path: Path) -> None:
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(SOURCE_AND_TEST_DIFF, encoding="utf-8")
        report = build_report_from_file(diff_file)
        assert report.context.total_files == 2

    def test_from_file_line_counts(self, tmp_path: Path) -> None:
        diff_file = tmp_path / "migration.diff"
        diff_file.write_text(MIGRATION_DIFF, encoding="utf-8")
        report = build_report_from_file(diff_file)
        assert report.context.total_additions == 3
        assert report.context.total_deletions == 0

    def test_from_file_missing_path_raises_value_error(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist.diff"
        with pytest.raises(ValueError, match="Cannot read"):
            build_report_from_file(nonexistent)

    def test_from_file_custom_title(self, tmp_path: Path) -> None:
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(SIMPLE_SOURCE_DIFF, encoding="utf-8")
        report = build_report_from_file(diff_file, title="My Custom Report")
        assert report.title == "My Custom Report"


# ---------------------------------------------------------------------------
# Test 13: Empty diff raises ValueError
# ---------------------------------------------------------------------------


class TestEmptyDiff:
    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_report_from_text("")

    def test_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            build_report_from_text("   \n\n  ")

    def test_binary_only_diff_raises_value_error(self) -> None:
        binary_diff = (
            "diff --git a/logo.png b/logo.png\n"
            "index abc..def 100644\n"
            "Binary files a/logo.png and b/logo.png differ\n"
        )
        with pytest.raises(ValueError):
            build_report_from_text(binary_diff)


# ---------------------------------------------------------------------------
# Test 14: generated_at is ISO 8601
# ---------------------------------------------------------------------------


class TestGeneratedAt:
    def test_generated_at_is_non_empty_string(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert isinstance(report.generated_at, str)
        assert len(report.generated_at) > 0

    def test_generated_at_contains_iso_separator(self) -> None:
        """ISO 8601 strings use 'T' as the date/time separator."""
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert "T" in report.generated_at

    def test_generated_at_contains_timezone_offset(self) -> None:
        """datetime.now(timezone.utc).isoformat() ends with '+00:00'."""
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert "+00:00" in report.generated_at or "Z" in report.generated_at


# ---------------------------------------------------------------------------
# Test 15: Custom title
# ---------------------------------------------------------------------------


class TestCustomTitle:
    def test_default_title_is_set(self) -> None:
        report = build_report_from_text(SIMPLE_SOURCE_DIFF)
        assert "ReviewPilot" in report.title

    def test_custom_title_is_used(self) -> None:
        report = build_report_from_text(
            SIMPLE_SOURCE_DIFF,
            title="Sprint 42 Review",
        )
        assert report.title == "Sprint 42 Review"


# ---------------------------------------------------------------------------
# Test 16: Custom AIClient can be injected
# ---------------------------------------------------------------------------


class TestCustomAIClient:
    def test_custom_client_is_called(self) -> None:
        spy = _RecordingAIClient()
        build_report_from_text(SIMPLE_SOURCE_DIFF, ai_client=spy)
        assert spy.call_count == 1

    def test_custom_client_receives_analysis_context(self) -> None:
        spy = _RecordingAIClient()
        build_report_from_text(SIMPLE_SOURCE_DIFF, ai_client=spy)
        assert isinstance(spy.last_context, AnalysisContext)

    def test_custom_client_context_has_no_raw_diff(self) -> None:
        """The AnalysisContext passed to the AI must not contain raw diff text."""
        spy = _RecordingAIClient()
        build_report_from_text(SIMPLE_SOURCE_DIFF, ai_client=spy)
        ctx = spy.last_context
        # AnalysisContext has no raw diff fields — verify by checking its structure
        assert not hasattr(ctx, "raw_diff")
        assert not hasattr(ctx, "diff_text")

    def test_custom_client_insights_appear_in_report(self) -> None:
        spy = _RecordingAIClient()
        report = build_report_from_text(SIMPLE_SOURCE_DIFF, ai_client=spy)
        assert report.ai_insights.regression_hypotheses == ["spy hypothesis"]
        assert report.ai_insights.test_suggestions == ["spy test"]
        assert report.ai_insights.reviewer_checklist == ["spy checklist"]
        assert report.ai_insights.assumptions == ["spy assumption"]

    def test_custom_client_satisfies_protocol(self) -> None:
        """_RecordingAIClient structurally satisfies the AIClient Protocol."""
        assert isinstance(_RecordingAIClient(), AIClient)
