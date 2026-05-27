"""
AI client module.

Responsibility: Define the AIClient interface (Protocol) and provide a
MockAIClient for offline use, testing, and demos.

Architecture constraint:
    The AI client NEVER receives raw diff text.
    It receives a structured AnalysisContext containing classified file
    summaries, risk scores, and detected patterns. This keeps prompts
    token-efficient, reproducible, and free of accidental data leakage.

AIClient (Protocol):
    Any class that implements generate_insights() satisfies this interface.
    The rest of the system programs against AIClient, not a concrete class,
    so the backend can be swapped without touching any other module.

MockAIClient:
    Deterministic offline implementation. Generates grounded AIInsights
    derived solely from data present in the AnalysisContext — it never
    invents file paths or symbols that are not in the input.
    Used in all tests and as the default for the CLI demo.

Real API integration (e.g. AnthropicAIClient) can be added in a later
commit by implementing the same Protocol without changing any other module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reviewpilot.models import AIInsights, AnalysisContext, FileRole, RiskLevel


# ---------------------------------------------------------------------------
# Protocol  (the public interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class AIClient(Protocol):
    """Protocol that all AI client implementations must satisfy.

    Implementations receive a structured AnalysisContext and return typed
    AIInsights. The Protocol is runtime-checkable so tests can use
    ``isinstance(client, AIClient)``.
    """

    def generate_insights(self, context: AnalysisContext) -> AIInsights:
        """Generate AI-assisted insights from a structured analysis context.

        Args:
            context: Structured diff analysis (file summaries, risk scores,
                     detected patterns). Never contains raw diff text.

        Returns:
            AIInsights with regression_hypotheses, test_suggestions,
            reviewer_checklist, and assumptions.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# MockAIClient
# ---------------------------------------------------------------------------


class MockAIClient:
    """Deterministic, offline AI client for testing and demos.

    Generates AIInsights grounded in the AnalysisContext:
      - Only references file paths that exist in context.file_summaries.
      - Never calls any external service.
      - Same context always produces the same output (deterministic).

    Satisfies AIClient via structural subtyping (duck typing / Protocol).

    Insight generation logic:
      HIGH / CRITICAL files   → file-specific regression hypothesis + targeted tests
      AUTH_SECURITY_KEYWORD   → auth edge-case test suggestion + security checklist item
      MIGRATION role          → migration validation suggestion + checklist item
      CONFIG / INFRA role     → deployment validation suggestion + checklist item
      NO_TEST_COVERAGE signal → coverage reminder in checklist
      Low-risk / empty        → conservative fallback suggestions
      Assumptions             → always populated (3 standard items)
    """

    def generate_insights(self, context: AnalysisContext) -> AIInsights:
        """Return deterministic AIInsights derived from the AnalysisContext."""
        return AIInsights(
            regression_hypotheses=_build_regression_hypotheses(context),
            test_suggestions=_build_test_suggestions(context),
            reviewer_checklist=_build_reviewer_checklist(context),
            assumptions=_build_assumptions(),
        )


# ---------------------------------------------------------------------------
# Private helpers — one function per AIInsights field
# ---------------------------------------------------------------------------


def _build_regression_hypotheses(context: AnalysisContext) -> list[str]:
    """Return regression hypotheses grounded in context.file_summaries.

    Only references display paths that exist in the context.
    Falls back to a conservative message when no high-risk files are found.
    """
    hypotheses: list[str] = []

    # File-specific hypotheses for HIGH / CRITICAL risk files
    for fs in context.file_summaries:
        if fs.risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            hypotheses.append(
                f"`{fs.diff_file.display_path}` ({fs.risk.level.value} risk, "
                f"score {fs.risk.score}): changes here may introduce regressions "
                f"in dependent modules — review call sites and downstream consumers."
            )

    # Auth/security hypothesis (global, not file-specific)
    if _has_signal(context, "AUTH_SECURITY_KEYWORD"):
        hypotheses.append(
            "Auth/security keywords detected in changed lines: access control "
            "behaviour may be altered. Verify all permission checks are still "
            "correctly enforced after these changes."
        )

    # Migration hypothesis (global)
    if _has_role(context, FileRole.MIGRATION):
        hypotheses.append(
            "Database schema migration detected: existing queries, ORM model "
            "mappings, and reports that depend on affected tables may break."
        )

    # Fallback for low-risk / empty diffs
    if not hypotheses:
        hypotheses.append(
            "No high-risk changes detected in this diff. "
            "Verify that existing behaviour is preserved by running the full test suite."
        )

    return hypotheses


def _build_test_suggestions(context: AnalysisContext) -> list[str]:
    """Return test suggestions grounded in context.file_summaries.

    Falls back to a general "run the test suite" suggestion when no
    specific risk factors are present.
    """
    suggestions: list[str] = []

    # Targeted tests for HIGH / CRITICAL risk files
    for fs in context.file_summaries:
        if fs.risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            suggestions.append(
                f"Add or extend unit tests for `{fs.diff_file.display_path}`: "
                f"cover changed code paths, edge cases, and newly introduced "
                f"error conditions."
            )

    # Auth edge-case tests
    if _has_signal(context, "AUTH_SECURITY_KEYWORD"):
        suggestions.append(
            "Test authentication/authorization edge cases: invalid tokens, "
            "expired credentials, permission boundary conditions, and privilege "
            "escalation attempts."
        )

    # Migration validation
    if _has_role(context, FileRole.MIGRATION):
        suggestions.append(
            "Run the migration forward on a staging database. Verify the "
            "resulting schema state, then confirm rollback is possible before "
            "merging to the main branch."
        )

    # Deployment validation for config / infra changes
    if _has_role(context, FileRole.CONFIG) or _has_role(context, FileRole.INFRA):
        suggestions.append(
            "Deploy to a staging environment and validate application start-up, "
            "configuration loading, and health check endpoints after these changes."
        )

    # Fallback for low-risk diffs
    if not suggestions:
        suggestions.append(
            "Run the full test suite to confirm existing behaviour is preserved. "
            "Consider adding a regression test if no test file was included in this diff."
        )

    return suggestions


def _build_reviewer_checklist(context: AnalysisContext) -> list[str]:
    """Return reviewer checklist items grounded in context.file_summaries.

    Falls back to a standard "sanity check" item when no specific risk
    factors are present.
    """
    checklist: list[str] = []

    # File-specific review items for HIGH / CRITICAL files
    for fs in context.file_summaries:
        if fs.risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            signal_labels = (
                ", ".join(s.label for s in fs.risk.signals) or "none"
            )
            checklist.append(
                f"Manually review `{fs.diff_file.display_path}` "
                f"(risk signals: {signal_labels}). "
                f"Check for unintended side effects, missing error handling, "
                f"and boundary conditions."
            )

    # Auth/security review
    if _has_signal(context, "AUTH_SECURITY_KEYWORD"):
        checklist.append(
            "Security review: confirm that authentication and permission logic "
            "is not weakened. Verify token handling, credential storage, and "
            "access control boundaries."
        )

    # Migration review
    if _has_role(context, FileRole.MIGRATION):
        checklist.append(
            "Migration review: check for irreversible operations (DROP, TRUNCATE, "
            "ALTER). Confirm a tested rollback plan is ready before deploying to "
            "production."
        )

    # Config / infra review
    if _has_role(context, FileRole.CONFIG) or _has_role(context, FileRole.INFRA):
        checklist.append(
            "Config/infrastructure review: validate changes across all environments "
            "(dev, staging, production). Confirm no secrets are hardcoded and "
            "deployment run-books are updated."
        )

    # No test coverage reminder
    if _has_signal(context, "NO_TEST_COVERAGE"):
        checklist.append(
            "No test file was included in this diff. Verify that existing tests "
            "still provide adequate coverage of the changed source code."
        )

    # Fallback for low-risk / no specific flags
    if not checklist:
        checklist.append(
            "Standard review: verify the changes match the stated intent, "
            "the code is readable and consistent with project conventions, "
            "and no obvious logic errors are present."
        )

    return checklist


def _build_assumptions() -> list[str]:
    """Return the standard set of mock AI assumptions.

    Always populated with 3 items regardless of context content, making
    the 'assumptions always present' invariant easy to test.
    """
    return [
        "This analysis is based on structured diff metadata (file paths, roles, "
        "risk scores, and keyword patterns). The mock AI client has not read the "
        "full source code or repository history.",
        "File role classifications and risk scores are heuristic estimates. "
        "Manual review may reveal additional concerns not captured by static "
        "keyword matching alone.",
        "All suggestions are AI-generated (mock output) and should be validated "
        "by a human reviewer before acting on them.",
    ]


# ---------------------------------------------------------------------------
# Context query utilities
# ---------------------------------------------------------------------------


def _has_signal(context: AnalysisContext, label: str) -> bool:
    """Return True if any file summary in the context has a signal with the given label."""
    return any(
        any(s.label == label for s in fs.risk.signals)
        for fs in context.file_summaries
    )


def _has_role(context: AnalysisContext, role: FileRole) -> bool:
    """Return True if any file summary in the context has the given FileRole."""
    return any(fs.role is role for fs in context.file_summaries)
