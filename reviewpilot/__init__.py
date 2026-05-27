"""
ReviewPilot: AI-assisted PR review and test planning CLI tool.

Analyzes a local git diff file and generates a structured Markdown report,
separating deterministic analysis (diff parsing, file classification, risk
scoring) from AI-assisted suggestions (regression hypotheses, test proposals,
reviewer checklist).

Usage:
    python -m reviewpilot <diff_file> [--output <report.md>]
"""

__version__ = "0.1.0"
__author__ = "IlayRomi"
