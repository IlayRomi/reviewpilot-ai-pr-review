"""
Data models for ReviewPilot.

All pipeline stages use typed dataclasses defined here. Reading this module
is the fastest way to understand the data flow through the system.

Pipeline data flow:
    .diff file
        → parser.py       → list[DiffFile]
        → classifier.py   → FileRole          (per file)
        → risk_scorer.py  → RiskScore         (per file)
        → report_builder  → FileSummary list + AnalysisContext
        → ai_client.py    → AIInsights
        → report_builder  → ReviewReport
        → renderer.py     → Markdown string

Deterministic models (no AI involvement):
    DiffLine, DiffHunk, DiffFile          — parsed diff representation
    FileRole, ChangeType, LineType        — classification enums
    RiskLevel, RiskSignal, RiskScore      — risk analysis results
    FileSummary                           — per-file combined result

AI boundary models:
    AnalysisContext   — structured input to the AI layer (never raw diff text)
    AIInsights        — typed output from the AI layer

Assembly model:
    ReviewReport      — final combined report, ready for rendering
"""

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LineType(Enum):
    """The type of a single line within a diff hunk."""

    ADDED = "added"
    REMOVED = "removed"
    CONTEXT = "context"


class ChangeType(Enum):
    """How a file changed between the old and new revisions."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNKNOWN = "unknown"


class FileRole(Enum):
    """The functional role of a file in the project.

    Used by the classifier to assign a category to each changed file.
    Role drives downstream risk-scoring weights.
    """

    SOURCE = "source"
    TEST = "test"
    CONFIG = "config"
    MIGRATION = "migration"
    DOCS = "docs"
    INFRA = "infra"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Coarse risk classification derived from the aggregate RiskScore.

    Score thresholds (defined in risk_scorer.py):
         0–20  → LOW
        21–50  → MEDIUM
        51–80  → HIGH
        81+    → CRITICAL
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Diff representation (output of parser.py)
# ---------------------------------------------------------------------------


@dataclass
class DiffLine:
    """A single line within a diff hunk.

    Attributes:
        content:   Raw line text (includes the leading +/- character for
                   added/removed lines, or a space for context lines).
        line_type: Whether this line was added, removed, or unchanged context.
    """

    content: str
    line_type: LineType


@dataclass
class DiffHunk:
    """A contiguous block of changes within a single file.

    Corresponds to one @@ ... @@ section in a unified diff.

    Attributes:
        old_start: First line number in the old file (None for new files).
        old_count: Number of lines from the old file in this hunk.
        new_start: First line number in the new file (None for deleted files).
        new_count: Number of lines in the new file in this hunk.
        lines:     Ordered list of DiffLine objects in this hunk.
    """

    old_start: int | None
    old_count: int | None
    new_start: int | None
    new_count: int | None
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class DiffFile:
    """All changes to a single file as parsed from the diff.

    Attributes:
        old_path:    File path in the old revision (None for newly added files).
        new_path:    File path in the new revision (None for deleted files).
        change_type: How the file changed (ADDED, MODIFIED, DELETED, etc.).
        hunks:       Ordered list of DiffHunk objects for this file.
        additions:   Total number of added lines across all hunks.
        deletions:   Total number of removed lines across all hunks.
    """

    old_path: str | None
    new_path: str | None
    change_type: ChangeType
    hunks: list[DiffHunk] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    @property
    def display_path(self) -> str:
        """The most useful path for display: new_path if present, else old_path."""
        return self.new_path or self.old_path or "<unknown>"

    @property
    def total_changes(self) -> int:
        """Sum of additions and deletions."""
        return self.additions + self.deletions


# ---------------------------------------------------------------------------
# Risk analysis (output of risk_scorer.py)
# ---------------------------------------------------------------------------


@dataclass
class RiskSignal:
    """A single deterministic signal that contributes to a file's risk score.

    Attributes:
        label:  Short identifier for the signal type (e.g., "LARGE_CHANGE").
        reason: Human-readable explanation suitable for the report.
        weight: Points added to the aggregate score (negative = risk reduction).
    """

    label: str
    reason: str
    weight: int


@dataclass
class RiskScore:
    """Aggregated deterministic risk score for a single changed file.

    Attributes:
        level:   Coarse classification derived from the numeric score.
        score:   Raw additive score from all triggered RiskSignals.
        signals: All signals that fired for this file (for report transparency).
    """

    level: RiskLevel
    score: int
    signals: list[RiskSignal] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-file combined result
# ---------------------------------------------------------------------------


@dataclass
class FileSummary:
    """Combined analysis result for a single changed file.

    Produced by the report_builder after parser → classifier → risk_scorer.

    Attributes:
        diff_file: Parsed diff data for this file.
        role:      Functional role assigned by the classifier.
        risk:      Deterministic risk score with all contributing signals.
    """

    diff_file: DiffFile
    role: FileRole
    risk: RiskScore


# ---------------------------------------------------------------------------
# AI layer boundary (input / output of ai_client.py)
# ---------------------------------------------------------------------------


@dataclass
class AnalysisContext:
    """Structured context passed to the AI layer.

    IMPORTANT: This object never contains raw diff text. Sending structured
    data (classifications, scores, patterns) instead of raw diffs keeps prompts
    token-efficient, reproducible, and inspectable.

    Attributes:
        file_summaries:    List of per-file analysis results.
        total_files:       Number of files changed in the diff.
        total_additions:   Total added lines across all files.
        total_deletions:   Total removed lines across all files.
        detected_patterns: Human-readable labels for patterns found in the diff
                           (e.g., "auth keywords", "destructive SQL").
    """

    file_summaries: list[FileSummary] = field(default_factory=list)
    total_files: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    detected_patterns: list[str] = field(default_factory=list)


@dataclass
class AIInsights:
    """AI-generated insights returned by the AI client.

    All fields contain suggestions, not facts. The renderer labels these
    sections clearly to preserve epistemic honesty.

    Attributes:
        regression_hypotheses: Areas of the codebase likely to regress.
        test_suggestions:      Specific tests recommended (unit/integration/manual).
        reviewer_checklist:    Items a human reviewer should verify.
        assumptions:           What the AI assumed about the codebase/context.
    """

    regression_hypotheses: list[str] = field(default_factory=list)
    test_suggestions: list[str] = field(default_factory=list)
    reviewer_checklist: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Final assembled report (input to renderer.py)
# ---------------------------------------------------------------------------


@dataclass
class ReviewReport:
    """The final assembled review report, ready for rendering to Markdown.

    Attributes:
        title:        Human-readable title for the report.
        generated_at: ISO 8601 timestamp string of when the report was built.
        context:      Full deterministic analysis context.
        ai_insights:  AI-generated suggestions (labeled as such in output).
    """

    title: str
    generated_at: str
    context: AnalysisContext
    ai_insights: AIInsights
