"""
Risk scorer module.

Responsibility: Given a DiffFile and its FileRole, compute a deterministic
RiskScore using additive, rule-based heuristics.

All scoring logic is transparent and unit-testable. Every signal that
contributes to the final score is captured in a RiskSignal with a human-readable
label and reason — so the report can explain *why* a file is considered risky.

Risk signals (additive weights, defined as constants):
    LARGE_CHANGE        — file has >200 lines changed               (+30)
    MIGRATION_FILE      — role is MIGRATION                         (+40)
    AUTH_KEYWORDS       — diff contains auth/security keywords      (+35)
    DESTRUCTIVE_SQL     — diff contains DROP/DELETE/TRUNCATE        (+40)
    NO_TEST_COVERAGE    — SOURCE changed, no TEST file in same diff (+20)
    CONFIG_CHANGE       — role is CONFIG                            (+15)
    INFRA_CHANGE        — role is INFRA                             (+20)
    TEST_ONLY_CHANGE    — only TEST files changed (risk reduction)  (-10)
    DOCS_ONLY_CHANGE    — only DOCS files changed (risk reduction)  (-20)

Score → RiskLevel mapping:
     0–20  → LOW
    21–50  → MEDIUM
    51–80  → HIGH
    81+    → CRITICAL

Public interface (to be implemented in Commit #5):
    score_file(diff_file: DiffFile, role: FileRole,
               all_roles: list[FileRole]) -> RiskScore
        Score a single file. `all_roles` is used for the NO_TEST_COVERAGE signal.

    score_all(file_summaries: list[FileSummary]) -> list[FileSummary]
        Score all files and return updated FileSummary objects.
"""

# Implementation will be added in Commit #5.
