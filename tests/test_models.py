"""
Tests for reviewpilot/models.py — Commit #2.

Coverage:
  - All enums: membership, string values, stability
  - All dataclasses: instantiation with required and optional fields
  - default_factory isolation: list fields on separate instances are independent
  - Computed properties: DiffFile.display_path, DiffFile.total_changes
"""

import pytest
from reviewpilot.models import (
    AIInsights,
    AnalysisContext,
    ChangeType,
    DiffFile,
    DiffHunk,
    DiffLine,
    FileSummary,
    FileRole,
    LineType,
    ReviewReport,
    RiskLevel,
    RiskScore,
    RiskSignal,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_diff_line(content: str = "+hello", line_type: LineType = LineType.ADDED) -> DiffLine:
    return DiffLine(content=content, line_type=line_type)


def make_diff_hunk() -> DiffHunk:
    return DiffHunk(old_start=1, old_count=3, new_start=1, new_count=4)


def make_diff_file(
    old_path: str | None = "src/app.py",
    new_path: str | None = "src/app.py",
    change_type: ChangeType = ChangeType.MODIFIED,
    additions: int = 5,
    deletions: int = 2,
) -> DiffFile:
    return DiffFile(
        old_path=old_path,
        new_path=new_path,
        change_type=change_type,
        additions=additions,
        deletions=deletions,
    )


def make_risk_score(
    level: RiskLevel = RiskLevel.LOW,
    score: int = 10,
) -> RiskScore:
    return RiskScore(level=level, score=score)


def make_file_summary() -> FileSummary:
    return FileSummary(
        diff_file=make_diff_file(),
        role=FileRole.SOURCE,
        risk=make_risk_score(),
    )


def make_analysis_context() -> AnalysisContext:
    return AnalysisContext(
        file_summaries=[make_file_summary()],
        total_files=1,
        total_additions=5,
        total_deletions=2,
        detected_patterns=["auth keywords"],
    )


def make_ai_insights() -> AIInsights:
    return AIInsights(
        regression_hypotheses=["Login flow may regress"],
        test_suggestions=["Test authentication handler"],
        reviewer_checklist=["Check token expiry logic"],
        assumptions=["Django authentication backend assumed"],
    )


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestLineType:
    def test_members_exist(self) -> None:
        assert LineType.ADDED
        assert LineType.REMOVED
        assert LineType.CONTEXT

    def test_string_values(self) -> None:
        assert LineType.ADDED.value == "added"
        assert LineType.REMOVED.value == "removed"
        assert LineType.CONTEXT.value == "context"

    def test_exactly_three_members(self) -> None:
        assert len(LineType) == 3

    def test_lookup_by_value(self) -> None:
        assert LineType("added") is LineType.ADDED
        assert LineType("removed") is LineType.REMOVED
        assert LineType("context") is LineType.CONTEXT


class TestChangeType:
    def test_members_exist(self) -> None:
        assert ChangeType.ADDED
        assert ChangeType.MODIFIED
        assert ChangeType.DELETED
        assert ChangeType.RENAMED
        assert ChangeType.UNKNOWN

    def test_string_values(self) -> None:
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.MODIFIED.value == "modified"
        assert ChangeType.DELETED.value == "deleted"
        assert ChangeType.RENAMED.value == "renamed"
        assert ChangeType.UNKNOWN.value == "unknown"

    def test_exactly_five_members(self) -> None:
        assert len(ChangeType) == 5


class TestFileRole:
    def test_members_exist(self) -> None:
        assert FileRole.SOURCE
        assert FileRole.TEST
        assert FileRole.CONFIG
        assert FileRole.MIGRATION
        assert FileRole.DOCS
        assert FileRole.INFRA
        assert FileRole.UNKNOWN

    def test_string_values(self) -> None:
        assert FileRole.SOURCE.value == "source"
        assert FileRole.TEST.value == "test"
        assert FileRole.CONFIG.value == "config"
        assert FileRole.MIGRATION.value == "migration"
        assert FileRole.DOCS.value == "docs"
        assert FileRole.INFRA.value == "infra"
        assert FileRole.UNKNOWN.value == "unknown"

    def test_exactly_seven_members(self) -> None:
        assert len(FileRole) == 7


class TestRiskLevel:
    def test_members_exist(self) -> None:
        assert RiskLevel.LOW
        assert RiskLevel.MEDIUM
        assert RiskLevel.HIGH
        assert RiskLevel.CRITICAL

    def test_string_values(self) -> None:
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_exactly_four_members(self) -> None:
        assert len(RiskLevel) == 4


# ---------------------------------------------------------------------------
# Dataclass instantiation tests
# ---------------------------------------------------------------------------


class TestDiffLine:
    def test_basic_instantiation(self) -> None:
        line = DiffLine(content="+hello world", line_type=LineType.ADDED)
        assert line.content == "+hello world"
        assert line.line_type is LineType.ADDED

    def test_removed_line(self) -> None:
        line = DiffLine(content="-old code", line_type=LineType.REMOVED)
        assert line.line_type is LineType.REMOVED

    def test_context_line(self) -> None:
        line = DiffLine(content=" unchanged", line_type=LineType.CONTEXT)
        assert line.line_type is LineType.CONTEXT


class TestDiffHunk:
    def test_basic_instantiation(self) -> None:
        hunk = DiffHunk(old_start=10, old_count=5, new_start=10, new_count=7)
        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 10
        assert hunk.new_count == 7
        assert hunk.lines == []

    def test_none_fields_for_new_file(self) -> None:
        hunk = DiffHunk(old_start=None, old_count=None, new_start=1, new_count=10)
        assert hunk.old_start is None
        assert hunk.old_count is None

    def test_lines_default_factory_isolation(self) -> None:
        """Two DiffHunk instances must not share the same lines list."""
        hunk_a = make_diff_hunk()
        hunk_b = make_diff_hunk()
        hunk_a.lines.append(make_diff_line())
        assert len(hunk_b.lines) == 0, "default_factory list was shared between instances"

    def test_with_lines(self) -> None:
        line = make_diff_line("+new line", LineType.ADDED)
        hunk = DiffHunk(old_start=1, old_count=0, new_start=1, new_count=1, lines=[line])
        assert len(hunk.lines) == 1
        assert hunk.lines[0].line_type is LineType.ADDED


class TestDiffFile:
    def test_basic_instantiation(self) -> None:
        df = make_diff_file()
        assert df.old_path == "src/app.py"
        assert df.new_path == "src/app.py"
        assert df.change_type is ChangeType.MODIFIED
        assert df.additions == 5
        assert df.deletions == 2
        assert df.hunks == []

    def test_added_file_no_old_path(self) -> None:
        df = DiffFile(old_path=None, new_path="src/new.py", change_type=ChangeType.ADDED)
        assert df.old_path is None
        assert df.new_path == "src/new.py"

    def test_deleted_file_no_new_path(self) -> None:
        df = DiffFile(old_path="src/old.py", new_path=None, change_type=ChangeType.DELETED)
        assert df.new_path is None

    def test_hunks_default_factory_isolation(self) -> None:
        """Two DiffFile instances must not share the same hunks list."""
        df_a = make_diff_file()
        df_b = make_diff_file()
        df_a.hunks.append(make_diff_hunk())
        assert len(df_b.hunks) == 0, "default_factory list was shared between instances"

    def test_display_path_prefers_new_path(self) -> None:
        df = make_diff_file(old_path="old/path.py", new_path="new/path.py")
        assert df.display_path == "new/path.py"

    def test_display_path_falls_back_to_old_path(self) -> None:
        df = DiffFile(old_path="src/deleted.py", new_path=None, change_type=ChangeType.DELETED)
        assert df.display_path == "src/deleted.py"

    def test_display_path_unknown_when_both_none(self) -> None:
        df = DiffFile(old_path=None, new_path=None, change_type=ChangeType.UNKNOWN)
        assert df.display_path == "<unknown>"

    def test_total_changes(self) -> None:
        df = make_diff_file(additions=10, deletions=3)
        assert df.total_changes == 13

    def test_total_changes_zero(self) -> None:
        df = DiffFile(old_path="f.py", new_path="f.py", change_type=ChangeType.MODIFIED)
        assert df.total_changes == 0


class TestRiskSignal:
    def test_basic_instantiation(self) -> None:
        signal = RiskSignal(
            label="LARGE_CHANGE",
            reason="File has 250 lines changed (threshold: 200)",
            weight=30,
        )
        assert signal.label == "LARGE_CHANGE"
        assert signal.reason == "File has 250 lines changed (threshold: 200)"
        assert signal.weight == 30

    def test_negative_weight_allowed(self) -> None:
        """Risk reduction signals use negative weights."""
        signal = RiskSignal(label="TEST_ONLY", reason="Only test files changed", weight=-10)
        assert signal.weight == -10


class TestRiskScore:
    def test_basic_instantiation(self) -> None:
        score = RiskScore(level=RiskLevel.HIGH, score=65)
        assert score.level is RiskLevel.HIGH
        assert score.score == 65
        assert score.signals == []

    def test_with_signals(self) -> None:
        sig = RiskSignal(label="MIGRATION_FILE", reason="Migration file detected", weight=40)
        score = RiskScore(level=RiskLevel.CRITICAL, score=90, signals=[sig])
        assert len(score.signals) == 1
        assert score.signals[0].label == "MIGRATION_FILE"

    def test_signals_default_factory_isolation(self) -> None:
        """Two RiskScore instances must not share the same signals list."""
        score_a = make_risk_score()
        score_b = make_risk_score()
        score_a.signals.append(RiskSignal(label="X", reason="y", weight=10))
        assert len(score_b.signals) == 0, "default_factory list was shared between instances"


class TestFileSummary:
    def test_basic_instantiation(self) -> None:
        summary = make_file_summary()
        assert summary.role is FileRole.SOURCE
        assert summary.risk.level is RiskLevel.LOW
        assert isinstance(summary.diff_file, DiffFile)

    def test_all_file_roles_accepted(self) -> None:
        for role in FileRole:
            summary = FileSummary(
                diff_file=make_diff_file(),
                role=role,
                risk=make_risk_score(),
            )
            assert summary.role is role


class TestAnalysisContext:
    def test_basic_instantiation(self) -> None:
        ctx = make_analysis_context()
        assert ctx.total_files == 1
        assert ctx.total_additions == 5
        assert ctx.total_deletions == 2
        assert "auth keywords" in ctx.detected_patterns
        assert len(ctx.file_summaries) == 1

    def test_empty_defaults(self) -> None:
        ctx = AnalysisContext()
        assert ctx.file_summaries == []
        assert ctx.total_files == 0
        assert ctx.total_additions == 0
        assert ctx.total_deletions == 0
        assert ctx.detected_patterns == []

    def test_file_summaries_default_factory_isolation(self) -> None:
        ctx_a = AnalysisContext()
        ctx_b = AnalysisContext()
        ctx_a.file_summaries.append(make_file_summary())
        assert len(ctx_b.file_summaries) == 0

    def test_detected_patterns_default_factory_isolation(self) -> None:
        ctx_a = AnalysisContext()
        ctx_b = AnalysisContext()
        ctx_a.detected_patterns.append("destructive SQL")
        assert len(ctx_b.detected_patterns) == 0


class TestAIInsights:
    def test_basic_instantiation(self) -> None:
        insights = make_ai_insights()
        assert len(insights.regression_hypotheses) == 1
        assert len(insights.test_suggestions) == 1
        assert len(insights.reviewer_checklist) == 1
        assert len(insights.assumptions) == 1

    def test_empty_defaults(self) -> None:
        insights = AIInsights()
        assert insights.regression_hypotheses == []
        assert insights.test_suggestions == []
        assert insights.reviewer_checklist == []
        assert insights.assumptions == []

    def test_all_list_fields_default_factory_isolation(self) -> None:
        a = AIInsights()
        b = AIInsights()
        a.regression_hypotheses.append("hypothesis")
        a.test_suggestions.append("test it")
        a.reviewer_checklist.append("check it")
        a.assumptions.append("assume this")
        assert b.regression_hypotheses == []
        assert b.test_suggestions == []
        assert b.reviewer_checklist == []
        assert b.assumptions == []


class TestReviewReport:
    def test_basic_instantiation(self) -> None:
        report = ReviewReport(
            title="Review: feature/auth-refactor",
            generated_at="2026-05-27T10:00:00Z",
            context=make_analysis_context(),
            ai_insights=make_ai_insights(),
        )
        assert report.title == "Review: feature/auth-refactor"
        assert report.generated_at == "2026-05-27T10:00:00Z"
        assert isinstance(report.context, AnalysisContext)
        assert isinstance(report.ai_insights, AIInsights)

    def test_context_and_insights_are_independent_instances(self) -> None:
        """Ensure report fields hold the exact objects passed in."""
        ctx = make_analysis_context()
        insights = make_ai_insights()
        report = ReviewReport(
            title="Test",
            generated_at="2026-05-27T00:00:00Z",
            context=ctx,
            ai_insights=insights,
        )
        assert report.context is ctx
        assert report.ai_insights is insights
