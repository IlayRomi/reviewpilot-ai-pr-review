"""
Tests for reviewpilot/ai_client.py — Commit #6.

MockAIClient is deterministic and grounded: all tests use hand-built
AnalysisContext objects (no real .diff files, no API calls).

Coverage:
  1.  MockAIClient returns a well-formed AIInsights object
  2.  AIClient Protocol is runtime-checkable; MockAIClient satisfies it
  3.  Empty / low-risk context returns conservative fallback suggestions
  4.  HIGH-risk file produces a file-specific regression hypothesis
  5.  CRITICAL-risk file appears in test suggestions
  6.  AUTH_SECURITY_KEYWORD signal produces auth-related test suggestion
  7.  MIGRATION role produces migration validation suggestion + checklist item
  8.  INFRA role produces deployment/environment checklist item
  9.  CONFIG role produces deployment/environment checklist item
  10. NO_TEST_COVERAGE signal produces coverage reminder in checklist
  11. MockAIClient does not invent file paths absent from context
  12. Mentioned file path in hypothesis matches the one in context
  13. Output is deterministic for the same input (call twice → identical)
  14. Assumptions are always present and non-empty
  15. Assumptions are present even for an empty context
  16. Multiple HIGH-risk files produce one hypothesis each
"""

import pytest

from reviewpilot.ai_client import AIClient, MockAIClient
from reviewpilot.models import (
    AnalysisContext,
    ChangeType,
    DiffFile,
    FileRole,
    FileSummary,
    RiskLevel,
    RiskScore,
    RiskSignal,
)


# ---------------------------------------------------------------------------
# Helpers — factory functions for building AnalysisContext in tests
# ---------------------------------------------------------------------------


def _make_diff_file(path: str = "src/app.py") -> DiffFile:
    return DiffFile(
        old_path=path,
        new_path=path,
        change_type=ChangeType.MODIFIED,
        additions=5,
        deletions=2,
    )


def _make_risk_score(
    level: RiskLevel = RiskLevel.LOW,
    score: int = 10,
    signal_labels: list[str] | None = None,
) -> RiskScore:
    signals = [
        RiskSignal(label=lbl, reason=f"test signal for {lbl}", weight=10)
        for lbl in (signal_labels or [])
    ]
    return RiskScore(level=level, score=score, signals=signals)


def _make_file_summary(
    path: str = "src/app.py",
    role: FileRole = FileRole.SOURCE,
    level: RiskLevel = RiskLevel.LOW,
    score: int = 10,
    signal_labels: list[str] | None = None,
) -> FileSummary:
    return FileSummary(
        diff_file=_make_diff_file(path),
        role=role,
        risk=_make_risk_score(level=level, score=score, signal_labels=signal_labels),
    )


def _make_context(*summaries: FileSummary) -> AnalysisContext:
    total_adds = sum(fs.diff_file.additions for fs in summaries)
    total_dels = sum(fs.diff_file.deletions for fs in summaries)
    return AnalysisContext(
        file_summaries=list(summaries),
        total_files=len(summaries),
        total_additions=total_adds,
        total_deletions=total_dels,
    )


# ---------------------------------------------------------------------------
# Test 1: Basic return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_ai_insights_object(self) -> None:
        from reviewpilot.models import AIInsights
        result = MockAIClient().generate_insights(AnalysisContext())
        assert isinstance(result, AIInsights)

    def test_all_fields_are_lists(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        assert isinstance(result.regression_hypotheses, list)
        assert isinstance(result.test_suggestions, list)
        assert isinstance(result.reviewer_checklist, list)
        assert isinstance(result.assumptions, list)

    def test_all_list_items_are_strings(self) -> None:
        ctx = _make_context(
            _make_file_summary(level=RiskLevel.HIGH, score=65)
        )
        result = MockAIClient().generate_insights(ctx)
        for field in (
            result.regression_hypotheses,
            result.test_suggestions,
            result.reviewer_checklist,
            result.assumptions,
        ):
            assert all(isinstance(item, str) for item in field)


# ---------------------------------------------------------------------------
# Test 2: Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_mock_client_satisfies_ai_client_protocol(self) -> None:
        """MockAIClient must satisfy AIClient at runtime (structural subtyping)."""
        client = MockAIClient()
        assert isinstance(client, AIClient)

    def test_generate_insights_is_callable(self) -> None:
        client = MockAIClient()
        assert callable(client.generate_insights)


# ---------------------------------------------------------------------------
# Test 3: Empty / low-risk context → conservative fallback
# ---------------------------------------------------------------------------


class TestLowRiskContext:
    def test_empty_context_produces_non_empty_hypotheses(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        assert len(result.regression_hypotheses) >= 1

    def test_empty_context_produces_non_empty_suggestions(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        assert len(result.test_suggestions) >= 1

    def test_empty_context_produces_non_empty_checklist(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        assert len(result.reviewer_checklist) >= 1

    def test_low_risk_context_uses_fallback_hypothesis(self) -> None:
        ctx = _make_context(_make_file_summary(level=RiskLevel.LOW, score=5))
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses).lower()
        assert "no high-risk" in combined or "test suite" in combined

    def test_low_risk_context_uses_fallback_suggestion(self) -> None:
        ctx = _make_context(_make_file_summary(level=RiskLevel.LOW, score=5))
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.test_suggestions).lower()
        assert "test suite" in combined or "regression test" in combined

    def test_low_risk_context_uses_fallback_checklist(self) -> None:
        ctx = _make_context(_make_file_summary(level=RiskLevel.LOW, score=5))
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.reviewer_checklist).lower()
        assert "standard review" in combined or "verify" in combined


# ---------------------------------------------------------------------------
# Test 4: HIGH-risk file → file-specific regression hypothesis
# ---------------------------------------------------------------------------


class TestHighRiskHypothesis:
    def test_high_risk_file_appears_in_hypothesis(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/billing.py", level=RiskLevel.HIGH, score=65)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        assert "src/billing.py" in combined

    def test_hypothesis_mentions_risk_level(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/billing.py", level=RiskLevel.HIGH, score=65)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        assert "high" in combined.lower()

    def test_critical_risk_file_appears_in_hypothesis(self) -> None:
        ctx = _make_context(
            _make_file_summary("migrations/001.sql", role=FileRole.MIGRATION,
                               level=RiskLevel.CRITICAL, score=110)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        assert "migrations/001.sql" in combined


# ---------------------------------------------------------------------------
# Test 5: HIGH/CRITICAL file appears in test suggestions
# ---------------------------------------------------------------------------


class TestHighRiskTestSuggestions:
    def test_high_risk_file_appears_in_test_suggestions(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/payments.py", level=RiskLevel.HIGH, score=70)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.test_suggestions)
        assert "src/payments.py" in combined

    def test_critical_file_appears_in_test_suggestions(self) -> None:
        ctx = _make_context(
            _make_file_summary("db/migrate.py", level=RiskLevel.CRITICAL, score=85)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.test_suggestions)
        assert "db/migrate.py" in combined


# ---------------------------------------------------------------------------
# Test 6: AUTH_SECURITY_KEYWORD → auth-related test suggestion
# ---------------------------------------------------------------------------


class TestAuthKeywordInsights:
    def _auth_context(self) -> AnalysisContext:
        return _make_context(
            _make_file_summary(
                "src/auth.py",
                level=RiskLevel.MEDIUM,
                score=35,
                signal_labels=["AUTH_SECURITY_KEYWORD"],
            )
        )

    def test_auth_signal_produces_auth_test_suggestion(self) -> None:
        result = MockAIClient().generate_insights(self._auth_context())
        combined = " ".join(result.test_suggestions).lower()
        assert "auth" in combined or "token" in combined or "credential" in combined

    def test_auth_signal_produces_security_checklist_item(self) -> None:
        result = MockAIClient().generate_insights(self._auth_context())
        combined = " ".join(result.reviewer_checklist).lower()
        assert "security" in combined or "auth" in combined or "permission" in combined

    def test_auth_signal_produces_auth_hypothesis(self) -> None:
        result = MockAIClient().generate_insights(self._auth_context())
        combined = " ".join(result.regression_hypotheses).lower()
        assert "auth" in combined or "permission" in combined or "access control" in combined


# ---------------------------------------------------------------------------
# Test 7: MIGRATION role → migration-related suggestions
# ---------------------------------------------------------------------------


class TestMigrationInsights:
    def _migration_context(self) -> AnalysisContext:
        return _make_context(
            _make_file_summary(
                "migrations/001_add_users.sql",
                role=FileRole.MIGRATION,
                level=RiskLevel.MEDIUM,
                score=40,
                signal_labels=["MIGRATION_FILE"],
            )
        )

    def test_migration_produces_migration_test_suggestion(self) -> None:
        result = MockAIClient().generate_insights(self._migration_context())
        combined = " ".join(result.test_suggestions).lower()
        assert "migration" in combined or "staging" in combined or "rollback" in combined

    def test_migration_produces_migration_checklist_item(self) -> None:
        result = MockAIClient().generate_insights(self._migration_context())
        combined = " ".join(result.reviewer_checklist).lower()
        assert "migration" in combined or "rollback" in combined or "irreversible" in combined

    def test_migration_appears_in_hypothesis(self) -> None:
        result = MockAIClient().generate_insights(self._migration_context())
        combined = " ".join(result.regression_hypotheses).lower()
        assert "migration" in combined or "schema" in combined


# ---------------------------------------------------------------------------
# Test 8: INFRA role → deployment/environment checklist item
# ---------------------------------------------------------------------------


class TestInfraInsights:
    def _infra_context(self) -> AnalysisContext:
        return _make_context(
            _make_file_summary(
                "Dockerfile",
                role=FileRole.INFRA,
                level=RiskLevel.LOW,
                score=20,
                signal_labels=["INFRA_CHANGE"],
            )
        )

    def test_infra_produces_deployment_suggestion(self) -> None:
        result = MockAIClient().generate_insights(self._infra_context())
        combined = " ".join(result.test_suggestions).lower()
        assert "deploy" in combined or "staging" in combined or "environment" in combined

    def test_infra_produces_checklist_item(self) -> None:
        result = MockAIClient().generate_insights(self._infra_context())
        combined = " ".join(result.reviewer_checklist).lower()
        assert "infrastructure" in combined or "deploy" in combined or "environment" in combined


# ---------------------------------------------------------------------------
# Test 9: CONFIG role → deployment/environment checklist item
# ---------------------------------------------------------------------------


class TestConfigInsights:
    def _config_context(self) -> AnalysisContext:
        return _make_context(
            _make_file_summary(
                "pyproject.toml",
                role=FileRole.CONFIG,
                level=RiskLevel.LOW,
                score=15,
                signal_labels=["CONFIG_CHANGE"],
            )
        )

    def test_config_produces_deployment_suggestion(self) -> None:
        result = MockAIClient().generate_insights(self._config_context())
        combined = " ".join(result.test_suggestions).lower()
        assert "deploy" in combined or "staging" in combined or "configuration" in combined

    def test_config_produces_checklist_item(self) -> None:
        result = MockAIClient().generate_insights(self._config_context())
        combined = " ".join(result.reviewer_checklist).lower()
        assert "config" in combined or "environment" in combined or "secrets" in combined


# ---------------------------------------------------------------------------
# Test 10: NO_TEST_COVERAGE signal → coverage reminder in checklist
# ---------------------------------------------------------------------------


class TestNoTestCoverageSignal:
    def test_no_test_coverage_signal_produces_checklist_reminder(self) -> None:
        ctx = _make_context(
            _make_file_summary(
                "src/service.py",
                role=FileRole.SOURCE,
                level=RiskLevel.LOW,
                score=20,
                signal_labels=["NO_TEST_COVERAGE"],
            )
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.reviewer_checklist).lower()
        assert "test" in combined and ("coverage" in combined or "no test" in combined)


# ---------------------------------------------------------------------------
# Test 11: Does not invent unknown file paths
# ---------------------------------------------------------------------------


class TestGroundedOutput:
    def test_empty_context_has_no_backtick_paths_in_hypotheses(self) -> None:
        """With no file summaries, no file paths should be mentioned."""
        result = MockAIClient().generate_insights(AnalysisContext())
        for hyp in result.regression_hypotheses:
            # No backtick-wrapped path segments should appear
            assert "`src/" not in hyp
            assert "`lib/" not in hyp
            assert "`migrations/" not in hyp

    def test_empty_context_has_no_backtick_paths_in_suggestions(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        for suggestion in result.test_suggestions:
            assert "`src/" not in suggestion
            assert "`lib/" not in suggestion

    def test_empty_context_has_no_backtick_paths_in_checklist(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        for item in result.reviewer_checklist:
            assert "`src/" not in item
            assert "`lib/" not in item


# ---------------------------------------------------------------------------
# Test 12: Mentioned path matches the one from context
# ---------------------------------------------------------------------------


class TestMentionedPathMatchesContext:
    def test_high_risk_path_appears_verbatim_in_hypothesis(self) -> None:
        unique_path = "src/very_specific_module_xyz.py"
        ctx = _make_context(
            _make_file_summary(unique_path, level=RiskLevel.HIGH, score=65)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        assert unique_path in combined

    def test_high_risk_path_appears_verbatim_in_test_suggestions(self) -> None:
        unique_path = "src/very_specific_module_xyz.py"
        ctx = _make_context(
            _make_file_summary(unique_path, level=RiskLevel.HIGH, score=65)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.test_suggestions)
        assert unique_path in combined

    def test_high_risk_path_appears_in_checklist(self) -> None:
        unique_path = "src/very_specific_module_xyz.py"
        ctx = _make_context(
            _make_file_summary(unique_path, level=RiskLevel.HIGH, score=65)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.reviewer_checklist)
        assert unique_path in combined

    def test_low_risk_path_does_not_appear_in_hypothesis(self) -> None:
        """LOW-risk files should not generate file-specific hypotheses."""
        unique_path = "src/low_risk_module.py"
        ctx = _make_context(
            _make_file_summary(unique_path, level=RiskLevel.LOW, score=5)
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        assert unique_path not in combined


# ---------------------------------------------------------------------------
# Test 13: Deterministic output for same input
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_context_produces_identical_hypotheses(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/auth.py", level=RiskLevel.HIGH, score=65,
                               signal_labels=["AUTH_SECURITY_KEYWORD"])
        )
        client = MockAIClient()
        result_a = client.generate_insights(ctx)
        result_b = client.generate_insights(ctx)
        assert result_a.regression_hypotheses == result_b.regression_hypotheses

    def test_same_context_produces_identical_suggestions(self) -> None:
        ctx = _make_context(
            _make_file_summary("migrations/001.sql", role=FileRole.MIGRATION,
                               level=RiskLevel.MEDIUM, score=40)
        )
        client = MockAIClient()
        assert client.generate_insights(ctx).test_suggestions == \
               client.generate_insights(ctx).test_suggestions

    def test_same_context_produces_identical_checklist(self) -> None:
        ctx = _make_context(_make_file_summary(level=RiskLevel.LOW))
        client = MockAIClient()
        assert client.generate_insights(ctx).reviewer_checklist == \
               client.generate_insights(ctx).reviewer_checklist

    def test_different_paths_produce_different_hypotheses(self) -> None:
        ctx_a = _make_context(_make_file_summary("src/module_a.py", level=RiskLevel.HIGH, score=65))
        ctx_b = _make_context(_make_file_summary("src/module_b.py", level=RiskLevel.HIGH, score=65))
        client = MockAIClient()
        hyp_a = client.generate_insights(ctx_a).regression_hypotheses
        hyp_b = client.generate_insights(ctx_b).regression_hypotheses
        assert hyp_a != hyp_b


# ---------------------------------------------------------------------------
# Tests 14 & 15: Assumptions always present
# ---------------------------------------------------------------------------


class TestAssumptions:
    def test_assumptions_non_empty_for_empty_context(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        assert len(result.assumptions) >= 1

    def test_assumptions_non_empty_for_high_risk_context(self) -> None:
        ctx = _make_context(_make_file_summary(level=RiskLevel.CRITICAL, score=110))
        result = MockAIClient().generate_insights(ctx)
        assert len(result.assumptions) >= 1

    def test_assumptions_are_non_empty_strings(self) -> None:
        result = MockAIClient().generate_insights(AnalysisContext())
        assert all(len(a.strip()) > 0 for a in result.assumptions)

    def test_assumptions_mention_mock_or_heuristic(self) -> None:
        """Assumptions should acknowledge they are mock/heuristic output."""
        result = MockAIClient().generate_insights(AnalysisContext())
        combined = " ".join(result.assumptions).lower()
        assert "mock" in combined or "heuristic" in combined or "metadata" in combined

    def test_exactly_three_standard_assumptions(self) -> None:
        """MockAIClient always returns exactly 3 standard assumptions."""
        result = MockAIClient().generate_insights(AnalysisContext())
        assert len(result.assumptions) == 3


# ---------------------------------------------------------------------------
# Test 16: Multiple HIGH-risk files each get their own hypothesis
# ---------------------------------------------------------------------------


class TestMultipleHighRiskFiles:
    def test_two_high_risk_files_each_mentioned(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/auth.py", level=RiskLevel.HIGH, score=65),
            _make_file_summary("src/payments.py", level=RiskLevel.CRITICAL, score=95),
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        assert "src/auth.py" in combined
        assert "src/payments.py" in combined

    def test_two_high_risk_files_produce_two_file_hypotheses(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/auth.py", level=RiskLevel.HIGH, score=65),
            _make_file_summary("src/payments.py", level=RiskLevel.CRITICAL, score=95),
        )
        result = MockAIClient().generate_insights(ctx)
        # Each high/critical file gets its own hypothesis (may have more for auth/migration)
        file_specific = [h for h in result.regression_hypotheses if "score" in h]
        assert len(file_specific) == 2

    def test_low_risk_file_alongside_high_risk_not_mentioned(self) -> None:
        ctx = _make_context(
            _make_file_summary("src/auth.py", level=RiskLevel.HIGH, score=65),
            _make_file_summary("src/utils.py", level=RiskLevel.LOW, score=5),
        )
        result = MockAIClient().generate_insights(ctx)
        combined = " ".join(result.regression_hypotheses)
        # Low-risk file should not appear in hypotheses
        assert "src/utils.py" not in combined
