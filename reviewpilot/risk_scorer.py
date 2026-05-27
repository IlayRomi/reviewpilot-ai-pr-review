"""
Risk scorer module.

Responsibility: Given a DiffFile and its FileRole, compute a deterministic
RiskScore using additive, rule-based heuristics. Every triggered rule is
captured as a RiskSignal with a human-readable reason so the report can
explain *why* a file is considered risky.

All scoring logic is transparent and unit-testable without an LLM.

Public interface:
    score_file(diff_file, role, all_roles=None) -> RiskScore
        Score a single file. `all_roles` is the list of FileRoles for every
        file in the diff — used to detect missing test coverage.

Score → RiskLevel mapping:
     0–20  LOW
    21–50  MEDIUM
    51–80  HIGH
    81+    CRITICAL

The final numeric score is clamped to a minimum of 0 (negative signals
reduce score but cannot produce a negative result).
"""

from __future__ import annotations

from reviewpilot.models import (
    DiffFile,
    FileRole,
    LineType,
    RiskLevel,
    RiskScore,
    RiskSignal,
)


# ---------------------------------------------------------------------------
# Signal weights — module-level constants for transparency and easy tuning
# ---------------------------------------------------------------------------

_WEIGHT_LARGE_CHANGE: int = 30
_WEIGHT_MIGRATION_FILE: int = 40
_WEIGHT_AUTH_SECURITY_KEYWORD: int = 35
_WEIGHT_DESTRUCTIVE_SQL: int = 40
_WEIGHT_NO_TEST_COVERAGE: int = 20
_WEIGHT_CONFIG_CHANGE: int = 15
_WEIGHT_INFRA_CHANGE: int = 20
_WEIGHT_TEST_ONLY_CHANGE: int = -10
_WEIGHT_DOCS_ONLY_CHANGE: int = -20

_LARGE_CHANGE_THRESHOLD: int = 200

# ---------------------------------------------------------------------------
# Keyword sets (all lowercase — matched against lowercased diff content)
# ---------------------------------------------------------------------------

_AUTH_KEYWORDS: frozenset[str] = frozenset(
    {"auth", "password", "token", "secret", "permission", "jwt", "credential"}
)

_DESTRUCTIVE_SQL_KEYWORDS: frozenset[str] = frozenset(
    {"drop", "delete", "truncate", "alter table"}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_file(
    diff_file: DiffFile,
    role: FileRole,
    all_roles: list[FileRole] | None = None,
) -> RiskScore:
    """Compute a deterministic RiskScore for a single changed file.

    Each rule that fires appends one RiskSignal to the result. The final
    score is the sum of all signal weights, clamped to a minimum of 0.

    Args:
        diff_file:  Parsed diff data for the file being scored.
        role:       FileRole assigned by the classifier for this file.
        all_roles:  FileRole values for *every* file in the diff (used to
                    detect missing test coverage). Pass None if unknown.

    Returns:
        A RiskScore with level, numeric score, and list of RiskSignals.
    """
    signals: list[RiskSignal] = []

    # ── Rule 1: Large change ──────────────────────────────────────────────
    if diff_file.total_changes > _LARGE_CHANGE_THRESHOLD:
        signals.append(
            RiskSignal(
                label="LARGE_CHANGE",
                reason=(
                    f"File has {diff_file.total_changes} changed lines "
                    f"(threshold: {_LARGE_CHANGE_THRESHOLD})"
                ),
                weight=_WEIGHT_LARGE_CHANGE,
            )
        )

    # ── Rule 2: Migration file ────────────────────────────────────────────
    if role is FileRole.MIGRATION:
        signals.append(
            RiskSignal(
                label="MIGRATION_FILE",
                reason="Database migration file — schema changes are hard to reverse",
                weight=_WEIGHT_MIGRATION_FILE,
            )
        )

    # Collect changed line text once for both keyword rules below.
    changed_text = _collect_changed_text(diff_file)

    # ── Rule 3: Auth / security keywords ─────────────────────────────────
    found_auth = _find_keywords(changed_text, _AUTH_KEYWORDS)
    if found_auth:
        signals.append(
            RiskSignal(
                label="AUTH_SECURITY_KEYWORD",
                reason=(
                    "Auth/security keywords in changed lines: "
                    + ", ".join(sorted(found_auth))
                ),
                weight=_WEIGHT_AUTH_SECURITY_KEYWORD,
            )
        )

    # ── Rule 4: Destructive SQL ───────────────────────────────────────────
    found_sql = _find_keywords(changed_text, _DESTRUCTIVE_SQL_KEYWORDS)
    if found_sql:
        signals.append(
            RiskSignal(
                label="DESTRUCTIVE_SQL",
                reason=(
                    "Potentially destructive SQL in changed lines: "
                    + ", ".join(sorted(found_sql))
                ),
                weight=_WEIGHT_DESTRUCTIVE_SQL,
            )
        )

    # ── Rule 5: No test coverage ──────────────────────────────────────────
    if (
        role is FileRole.SOURCE
        and all_roles is not None
        and FileRole.TEST not in all_roles
    ):
        signals.append(
            RiskSignal(
                label="NO_TEST_COVERAGE",
                reason="Source file changed with no test file present in this diff",
                weight=_WEIGHT_NO_TEST_COVERAGE,
            )
        )

    # ── Rule 6: Config change ─────────────────────────────────────────────
    if role is FileRole.CONFIG:
        signals.append(
            RiskSignal(
                label="CONFIG_CHANGE",
                reason="Configuration file changed — may affect runtime behaviour",
                weight=_WEIGHT_CONFIG_CHANGE,
            )
        )

    # ── Rule 7: Infra change ──────────────────────────────────────────────
    if role is FileRole.INFRA:
        signals.append(
            RiskSignal(
                label="INFRA_CHANGE",
                reason="Infrastructure / CI file changed — may affect deployment",
                weight=_WEIGHT_INFRA_CHANGE,
            )
        )

    # ── Rule 8: Test-only change (risk reduction) ─────────────────────────
    if role is FileRole.TEST:
        signals.append(
            RiskSignal(
                label="TEST_ONLY_CHANGE",
                reason="Only test files changed — lower production risk",
                weight=_WEIGHT_TEST_ONLY_CHANGE,
            )
        )

    # ── Rule 9: Docs-only change (risk reduction) ─────────────────────────
    if role is FileRole.DOCS:
        signals.append(
            RiskSignal(
                label="DOCS_ONLY_CHANGE",
                reason="Only documentation files changed — minimal production risk",
                weight=_WEIGHT_DOCS_ONLY_CHANGE,
            )
        )

    # ── Aggregate ─────────────────────────────────────────────────────────
    raw_score = sum(s.weight for s in signals)
    score = max(0, raw_score)  # clamp: score cannot be negative
    level = _score_to_level(score)

    return RiskScore(level=level, score=score, signals=signals)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_changed_text(diff_file: DiffFile) -> str:
    """Return all added and removed line content as one lowercased string.

    Only ADDED and REMOVED lines are included — context lines represent
    unchanged code and are irrelevant for keyword-based risk detection.
    """
    parts: list[str] = []
    for hunk in diff_file.hunks:
        for line in hunk.lines:
            if line.line_type in (LineType.ADDED, LineType.REMOVED):
                parts.append(line.content)
    return "\n".join(parts).lower()


def _find_keywords(text: str, keywords: frozenset[str]) -> set[str]:
    """Return the subset of keywords found in text via case-insensitive substring match.

    Because text is already lowercased (from _collect_changed_text) and
    keywords are lowercase constants, this is a simple membership check.

    Returns an empty set when no keywords match — callers use truthiness.
    """
    return {kw for kw in keywords if kw in text}


def _score_to_level(score: int) -> RiskLevel:
    """Map a non-negative integer score to a coarse RiskLevel bucket.

    Boundaries:
         0–20  → LOW
        21–50  → MEDIUM
        51–80  → HIGH
        81+    → CRITICAL
    """
    if score <= 20:
        return RiskLevel.LOW
    if score <= 50:
        return RiskLevel.MEDIUM
    if score <= 80:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL
