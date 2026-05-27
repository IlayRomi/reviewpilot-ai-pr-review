"""
Tests for reviewpilot/risk_scorer.py — Commit #5.

All tests use hand-built DiffFile objects; no real .diff files are needed.
Each test verifies both the numeric score/level AND the specific signals
that fired — ensuring the scoring is transparent, not just numerically correct.

Coverage:
  1.  No signals fire                          → score 0, LOW
  2.  Large change (>200 lines)                → LARGE_CHANGE +30, MEDIUM
  3.  Migration file role                      → MIGRATION_FILE +40, MEDIUM
  4.  Auth/security keyword in diff            → AUTH_SECURITY_KEYWORD +35, MEDIUM
  5.  Destructive SQL keyword in diff          → DESTRUCTIVE_SQL +40, MEDIUM
  6.  SOURCE without TEST in all_roles         → NO_TEST_COVERAGE +20
  7.  SOURCE with TEST in all_roles            → no NO_TEST_COVERAGE signal
  8.  all_roles=None                           → no NO_TEST_COVERAGE signal
  9.  CONFIG file role                         → CONFIG_CHANGE +15, LOW
  10. INFRA file role                          → INFRA_CHANGE +20, LOW
  11. TEST file role                           → TEST_ONLY_CHANGE, score clamped to 0
  12. DOCS file role                           → DOCS_ONLY_CHANGE, score clamped to 0
  13. Multiple signals combine additively      → correct sum
  14. Combined score ≥ 81 maps to CRITICAL
  15. Keywords not duplicated (signal fires once even if keyword appears many times)
  16. Case-insensitive keyword detection
  17. Context lines are ignored for keyword detection
  18. Score level boundary values (20/21, 50/51, 80/81)
"""

import pytest

from reviewpilot.models import (
    ChangeType,
    DiffFile,
    DiffHunk,
    DiffLine,
    FileRole,
    LineType,
    RiskLevel,
)
from reviewpilot.risk_scorer import _score_to_level, score_file


# ---------------------------------------------------------------------------
# Helpers — factory functions for building DiffFile objects in tests
# ---------------------------------------------------------------------------


def _make_diff_file(
    additions: int = 5,
    deletions: int = 2,
    added_lines: list[str] | None = None,
    removed_lines: list[str] | None = None,
    context_lines: list[str] | None = None,
) -> DiffFile:
    """Build a minimal DiffFile for testing.

    `additions` / `deletions` set the file-level counters directly.
    `added_lines`, `removed_lines`, `context_lines` populate hunk content
    (used to test keyword detection).
    """
    hunk = DiffHunk(old_start=1, old_count=deletions, new_start=1, new_count=additions)

    for content in added_lines or []:
        hunk.lines.append(DiffLine(content=f"+{content}", line_type=LineType.ADDED))
    for content in removed_lines or []:
        hunk.lines.append(DiffLine(content=f"-{content}", line_type=LineType.REMOVED))
    for content in context_lines or []:
        hunk.lines.append(DiffLine(content=f" {content}", line_type=LineType.CONTEXT))

    return DiffFile(
        old_path="src/module.py",
        new_path="src/module.py",
        change_type=ChangeType.MODIFIED,
        hunks=[hunk],
        additions=additions,
        deletions=deletions,
    )


def _make_large_diff_file() -> DiffFile:
    """DiffFile where total_changes > 200 (triggers LARGE_CHANGE)."""
    return _make_diff_file(additions=150, deletions=60)  # total = 210


def _signal_labels(risk_score) -> set[str]:
    """Return the set of signal labels from a RiskScore."""
    return {s.label for s in risk_score.signals}


# ---------------------------------------------------------------------------
# Test 1: No signals
# ---------------------------------------------------------------------------


class TestNoSignals:
    def test_unknown_role_small_diff_returns_low(self) -> None:
        df = _make_diff_file(additions=3, deletions=1)
        result = score_file(df, FileRole.UNKNOWN)
        assert result.level is RiskLevel.LOW
        assert result.score == 0
        assert result.signals == []

    def test_source_with_tests_present_no_keywords_returns_zero(self) -> None:
        df = _make_diff_file(added_lines=["x = 1"])
        result = score_file(df, FileRole.SOURCE, all_roles=[FileRole.SOURCE, FileRole.TEST])
        assert result.score == 0
        assert result.level is RiskLevel.LOW
        assert _signal_labels(result) == set()


# ---------------------------------------------------------------------------
# Test 2: LARGE_CHANGE signal
# ---------------------------------------------------------------------------


class TestLargeChange:
    def test_large_diff_triggers_signal(self) -> None:
        result = score_file(_make_large_diff_file(), FileRole.SOURCE)
        assert "LARGE_CHANGE" in _signal_labels(result)

    def test_large_diff_score_is_30(self) -> None:
        result = score_file(_make_large_diff_file(), FileRole.SOURCE)
        assert result.score == 30

    def test_large_diff_level_is_medium(self) -> None:
        result = score_file(_make_large_diff_file(), FileRole.SOURCE)
        assert result.level is RiskLevel.MEDIUM

    def test_below_threshold_no_signal(self) -> None:
        df = _make_diff_file(additions=100, deletions=99)  # total = 199
        result = score_file(df, FileRole.SOURCE)
        assert "LARGE_CHANGE" not in _signal_labels(result)

    def test_exactly_at_threshold_no_signal(self) -> None:
        df = _make_diff_file(additions=100, deletions=100)  # total = 200 (not > 200)
        result = score_file(df, FileRole.SOURCE)
        assert "LARGE_CHANGE" not in _signal_labels(result)

    def test_one_over_threshold_triggers_signal(self) -> None:
        df = _make_diff_file(additions=101, deletions=100)  # total = 201
        result = score_file(df, FileRole.SOURCE)
        assert "LARGE_CHANGE" in _signal_labels(result)

    def test_signal_reason_contains_line_count(self) -> None:
        df = _make_large_diff_file()
        result = score_file(df, FileRole.SOURCE)
        signal = next(s for s in result.signals if s.label == "LARGE_CHANGE")
        assert "210" in signal.reason


# ---------------------------------------------------------------------------
# Test 3: MIGRATION_FILE signal
# ---------------------------------------------------------------------------


class TestMigrationFile:
    def test_migration_role_triggers_signal(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.MIGRATION)
        assert "MIGRATION_FILE" in _signal_labels(result)

    def test_migration_score_is_40(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.MIGRATION)
        assert result.score == 40

    def test_migration_level_is_medium(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.MIGRATION)
        assert result.level is RiskLevel.MEDIUM


# ---------------------------------------------------------------------------
# Test 4: AUTH_SECURITY_KEYWORD signal
# ---------------------------------------------------------------------------


class TestAuthSecurityKeyword:
    def test_password_in_added_line(self) -> None:
        df = _make_diff_file(added_lines=["hashed_password = bcrypt.hash(pw)"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_token_in_added_line(self) -> None:
        df = _make_diff_file(added_lines=["access_token = generate_token()"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_auth_keyword_in_removed_line(self) -> None:
        df = _make_diff_file(removed_lines=["check_permission(user, resource)"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_jwt_keyword(self) -> None:
        df = _make_diff_file(added_lines=["decode_jwt(token_str)"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_auth_score_is_35(self) -> None:
        df = _make_diff_file(added_lines=["auth_check(user)"])
        result = score_file(df, FileRole.SOURCE)
        assert result.score == 35

    def test_auth_level_is_medium(self) -> None:
        df = _make_diff_file(added_lines=["auth_check(user)"])
        result = score_file(df, FileRole.SOURCE)
        assert result.level is RiskLevel.MEDIUM

    def test_matched_keywords_appear_in_reason(self) -> None:
        df = _make_diff_file(added_lines=["password = secret"])
        result = score_file(df, FileRole.SOURCE)
        signal = next(s for s in result.signals if s.label == "AUTH_SECURITY_KEYWORD")
        assert "password" in signal.reason or "secret" in signal.reason


# ---------------------------------------------------------------------------
# Test 5: DESTRUCTIVE_SQL signal
# ---------------------------------------------------------------------------


class TestDestructiveSQL:
    def test_drop_keyword(self) -> None:
        df = _make_diff_file(added_lines=["DROP TABLE old_users;"])
        result = score_file(df, FileRole.MIGRATION)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)

    def test_delete_keyword(self) -> None:
        df = _make_diff_file(added_lines=["DELETE FROM sessions WHERE expired=1;"])
        result = score_file(df, FileRole.MIGRATION)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)

    def test_truncate_keyword(self) -> None:
        df = _make_diff_file(added_lines=["TRUNCATE TABLE logs;"])
        result = score_file(df, FileRole.MIGRATION)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)

    def test_alter_table_keyword(self) -> None:
        df = _make_diff_file(added_lines=["ALTER TABLE users ADD COLUMN age INT;"])
        result = score_file(df, FileRole.MIGRATION)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)

    def test_destructive_sql_score_contribution_is_40(self) -> None:
        # Only SQL signal fires (MIGRATION adds separately)
        df = _make_diff_file(added_lines=["TRUNCATE TABLE cache;"])
        result = score_file(df, FileRole.SOURCE)
        sql_weight = next(s.weight for s in result.signals if s.label == "DESTRUCTIVE_SQL")
        assert sql_weight == 40


# ---------------------------------------------------------------------------
# Tests 6–8: NO_TEST_COVERAGE
# ---------------------------------------------------------------------------


class TestNoTestCoverage:
    def test_source_without_test_in_all_roles(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.SOURCE, all_roles=[FileRole.SOURCE])
        assert "NO_TEST_COVERAGE" in _signal_labels(result)

    def test_source_with_test_in_all_roles(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.SOURCE, all_roles=[FileRole.SOURCE, FileRole.TEST])
        assert "NO_TEST_COVERAGE" not in _signal_labels(result)

    def test_source_with_all_roles_none(self) -> None:
        """When all_roles is None (unknown), do NOT add NO_TEST_COVERAGE."""
        df = _make_diff_file()
        result = score_file(df, FileRole.SOURCE, all_roles=None)
        assert "NO_TEST_COVERAGE" not in _signal_labels(result)

    def test_no_test_coverage_weight_is_20(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.SOURCE, all_roles=[FileRole.SOURCE])
        signal = next(s for s in result.signals if s.label == "NO_TEST_COVERAGE")
        assert signal.weight == 20

    def test_non_source_roles_do_not_trigger_no_test_coverage(self) -> None:
        for role in (FileRole.TEST, FileRole.CONFIG, FileRole.DOCS, FileRole.MIGRATION):
            df = _make_diff_file()
            result = score_file(df, role, all_roles=[role])
            assert "NO_TEST_COVERAGE" not in _signal_labels(result), f"Unexpected signal for {role}"


# ---------------------------------------------------------------------------
# Test 9: CONFIG_CHANGE
# ---------------------------------------------------------------------------


class TestConfigChange:
    def test_config_role_triggers_signal(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.CONFIG)
        assert "CONFIG_CHANGE" in _signal_labels(result)

    def test_config_score_is_15(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.CONFIG)
        assert result.score == 15

    def test_config_level_is_low(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.CONFIG)
        assert result.level is RiskLevel.LOW


# ---------------------------------------------------------------------------
# Test 10: INFRA_CHANGE
# ---------------------------------------------------------------------------


class TestInfraChange:
    def test_infra_role_triggers_signal(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.INFRA)
        assert "INFRA_CHANGE" in _signal_labels(result)

    def test_infra_score_is_20(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.INFRA)
        assert result.score == 20

    def test_infra_level_is_low(self) -> None:
        """Score of 20 is still LOW (boundary: ≤ 20 → LOW)."""
        df = _make_diff_file()
        result = score_file(df, FileRole.INFRA)
        assert result.level is RiskLevel.LOW


# ---------------------------------------------------------------------------
# Test 11: TEST_ONLY_CHANGE (score clamped to 0)
# ---------------------------------------------------------------------------


class TestTestOnlyChange:
    def test_test_role_triggers_signal(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.TEST)
        assert "TEST_ONLY_CHANGE" in _signal_labels(result)

    def test_test_signal_weight_is_negative(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.TEST)
        signal = next(s for s in result.signals if s.label == "TEST_ONLY_CHANGE")
        assert signal.weight == -10

    def test_score_clamped_to_zero(self) -> None:
        """Raw score would be -10, but clamping gives 0."""
        df = _make_diff_file()
        result = score_file(df, FileRole.TEST)
        assert result.score == 0

    def test_level_is_low(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.TEST)
        assert result.level is RiskLevel.LOW


# ---------------------------------------------------------------------------
# Test 12: DOCS_ONLY_CHANGE (score clamped to 0)
# ---------------------------------------------------------------------------


class TestDocsOnlyChange:
    def test_docs_role_triggers_signal(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.DOCS)
        assert "DOCS_ONLY_CHANGE" in _signal_labels(result)

    def test_docs_signal_weight_is_negative(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.DOCS)
        signal = next(s for s in result.signals if s.label == "DOCS_ONLY_CHANGE")
        assert signal.weight == -20

    def test_score_clamped_to_zero(self) -> None:
        """Raw score would be -20, but clamping gives 0."""
        df = _make_diff_file()
        result = score_file(df, FileRole.DOCS)
        assert result.score == 0

    def test_level_is_low(self) -> None:
        df = _make_diff_file()
        result = score_file(df, FileRole.DOCS)
        assert result.level is RiskLevel.LOW


# ---------------------------------------------------------------------------
# Test 13: Multiple signals combine additively
# ---------------------------------------------------------------------------


class TestMultipleSignals:
    def test_migration_plus_large_change(self) -> None:
        # 40 + 30 = 70 → HIGH
        df = _make_large_diff_file()
        result = score_file(df, FileRole.MIGRATION)
        assert "MIGRATION_FILE" in _signal_labels(result)
        assert "LARGE_CHANGE" in _signal_labels(result)
        assert result.score == 70
        assert result.level is RiskLevel.HIGH

    def test_migration_plus_auth_keyword(self) -> None:
        # 40 + 35 = 75 → HIGH
        df = _make_diff_file(added_lines=["UPDATE users SET password = hash(pw)"])
        result = score_file(df, FileRole.MIGRATION)
        assert result.score == 75
        assert result.level is RiskLevel.HIGH

    def test_three_signals_sum_correctly(self) -> None:
        # MIGRATION(40) + DESTRUCTIVE_SQL(40) + LARGE_CHANGE(30) = 110 → CRITICAL
        df = _make_large_diff_file()
        df.hunks[0].lines.append(
            DiffLine(content="+DROP TABLE old_cache;", line_type=LineType.ADDED)
        )
        result = score_file(df, FileRole.MIGRATION)
        labels = _signal_labels(result)
        assert "MIGRATION_FILE" in labels
        assert "DESTRUCTIVE_SQL" in labels
        assert "LARGE_CHANGE" in labels
        assert result.score == 110


# ---------------------------------------------------------------------------
# Test 14: Score ≥ 81 maps to CRITICAL
# ---------------------------------------------------------------------------


class TestCriticalLevel:
    def test_score_81_is_critical(self) -> None:
        # MIGRATION(40) + DESTRUCTIVE_SQL(40) + LARGE_CHANGE(30) = 110 → CRITICAL
        df = _make_large_diff_file()
        df.hunks[0].lines.append(
            DiffLine(content="+TRUNCATE TABLE sessions;", line_type=LineType.ADDED)
        )
        result = score_file(df, FileRole.MIGRATION)
        assert result.level is RiskLevel.CRITICAL
        assert result.score >= 81

    def test_auth_plus_migration_plus_large_is_critical(self) -> None:
        # 35 + 40 + 30 = 105
        df = _make_large_diff_file()
        df.hunks[0].lines.append(
            DiffLine(content="+store_secret(token, credential)", line_type=LineType.ADDED)
        )
        result = score_file(df, FileRole.MIGRATION)
        assert result.level is RiskLevel.CRITICAL


# ---------------------------------------------------------------------------
# Test 15: Keyword signals are never duplicated
# ---------------------------------------------------------------------------


class TestNoDuplicateSignals:
    def test_multiple_password_occurrences_produce_one_signal(self) -> None:
        lines = [
            "password = hash(raw)",
            "old_password = hash(old_raw)",
            "new_password = hash(new_raw)",
            "confirm_password = hash(confirm_raw)",
        ]
        df = _make_diff_file(added_lines=lines)
        result = score_file(df, FileRole.SOURCE)
        auth_signals = [s for s in result.signals if s.label == "AUTH_SECURITY_KEYWORD"]
        assert len(auth_signals) == 1

    def test_multiple_drop_occurrences_produce_one_signal(self) -> None:
        lines = [
            "DROP TABLE table_a;",
            "DROP TABLE table_b;",
            "DROP TABLE table_c;",
        ]
        df = _make_diff_file(added_lines=lines)
        result = score_file(df, FileRole.MIGRATION)
        sql_signals = [s for s in result.signals if s.label == "DESTRUCTIVE_SQL"]
        assert len(sql_signals) == 1


# ---------------------------------------------------------------------------
# Test 16: Case-insensitive keyword detection
# ---------------------------------------------------------------------------


class TestCaseInsensitivity:
    def test_uppercase_password(self) -> None:
        df = _make_diff_file(added_lines=["PASSWORD = get_secret()"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_mixed_case_token(self) -> None:
        df = _make_diff_file(added_lines=["AccessToken = generate()"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_uppercase_drop(self) -> None:
        df = _make_diff_file(added_lines=["DROP TABLE users;"])
        result = score_file(df, FileRole.SOURCE)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)

    def test_lowercase_drop(self) -> None:
        df = _make_diff_file(added_lines=["drop table users;"])
        result = score_file(df, FileRole.SOURCE)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)

    def test_mixed_case_alter_table(self) -> None:
        df = _make_diff_file(added_lines=["Alter Table users ADD COLUMN age INT;"])
        result = score_file(df, FileRole.SOURCE)
        assert "DESTRUCTIVE_SQL" in _signal_labels(result)


# ---------------------------------------------------------------------------
# Test 17: Context lines are ignored for keyword detection
# ---------------------------------------------------------------------------


class TestContextLinesIgnored:
    def test_keyword_in_context_line_does_not_trigger(self) -> None:
        """A keyword appearing only in a CONTEXT line should not trigger a signal."""
        df = _make_diff_file(context_lines=["password_check = True"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" not in _signal_labels(result)

    def test_keyword_in_added_line_does_trigger(self) -> None:
        """Same keyword in an ADDED line should trigger the signal."""
        df = _make_diff_file(added_lines=["password_check = True"])
        result = score_file(df, FileRole.SOURCE)
        assert "AUTH_SECURITY_KEYWORD" in _signal_labels(result)

    def test_sql_keyword_in_context_line_does_not_trigger(self) -> None:
        df = _make_diff_file(context_lines=["# Note: DROP TABLE is dangerous"])
        result = score_file(df, FileRole.SOURCE)
        assert "DESTRUCTIVE_SQL" not in _signal_labels(result)


# ---------------------------------------------------------------------------
# Test 18: Score level boundary values
# ---------------------------------------------------------------------------


class TestScoreLevelBoundaries:
    """Verify _score_to_level at the exact boundaries: 20/21, 50/51, 80/81."""

    def test_score_0_is_low(self) -> None:
        assert _score_to_level(0) is RiskLevel.LOW

    def test_score_20_is_low(self) -> None:
        assert _score_to_level(20) is RiskLevel.LOW

    def test_score_21_is_medium(self) -> None:
        assert _score_to_level(21) is RiskLevel.MEDIUM

    def test_score_50_is_medium(self) -> None:
        assert _score_to_level(50) is RiskLevel.MEDIUM

    def test_score_51_is_high(self) -> None:
        assert _score_to_level(51) is RiskLevel.HIGH

    def test_score_80_is_high(self) -> None:
        assert _score_to_level(80) is RiskLevel.HIGH

    def test_score_81_is_critical(self) -> None:
        assert _score_to_level(81) is RiskLevel.CRITICAL

    def test_score_200_is_critical(self) -> None:
        assert _score_to_level(200) is RiskLevel.CRITICAL
