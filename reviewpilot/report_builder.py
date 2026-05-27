"""
Report builder module.

Responsibility: Orchestrate the full analysis pipeline and assemble the final
ReviewReport. This is the main integration point — all other modules are
stateless utilities called from here.

Pipeline steps:
    1. parser.parse_diff_text(text)    → List[DiffFile]
    2. classifier.classify_file(path)  → FileRole  (per file)
    3. risk_scorer.score_file(...)     → RiskScore (per file)
    4. Build AnalysisContext           (structured, no raw diff text)
    5. ai_client.generate_insights()   → AIInsights
    6. Assemble ReviewReport

The report builder does not contain business logic itself — it sequences calls
to the other modules and combines their outputs into the final data structure.

Public interface (to be implemented in Commit #7):
    build_report(
        diff_text: str,
        ai_client: AIClient,
        source_path: str = "",
    ) -> ReviewReport
        Run the full pipeline and return a ReviewReport.
"""

# Implementation will be added in Commit #7.
