"""
Data models for ReviewPilot.

All pipeline stages use typed dataclasses defined here. Reading this module
is the fastest way to understand the data flow through the system.

Pipeline data flow:
    .diff file
        → parser.py      → List[DiffFile]
        → classifier.py  → FileRole  (per file)
        → risk_scorer.py → RiskScore (per file)
        → report_builder → FileSummary (per file) + AnalysisContext
        → ai_client.py   → AIInsights
        → report_builder → ReviewReport
        → renderer.py    → Markdown string

Deterministic models (no AI involvement):
    DiffHunk, DiffFile, FileRole, RiskLevel, RiskSignal, RiskScore, FileSummary

AI boundary models:
    AnalysisContext  — structured input to the AI layer (never raw diff text)
    AIInsights       — typed output from the AI layer

Assembly model:
    ReviewReport     — final combined report, ready for rendering
"""

# Models will be implemented in Commit #2.
# This file intentionally contains no logic in the scaffold commit.
