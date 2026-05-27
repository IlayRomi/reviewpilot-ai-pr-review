"""
AI client module.

Responsibility: Define the AIClient interface (Protocol) and provide a
MockAIClient for offline use, testing, and demos.

Architecture constraint:
    The AI client NEVER receives raw diff text.
    It receives a structured AnalysisContext — a typed object containing:
      - classified file list with risk scores
      - overall diff statistics
      - detected keyword patterns
    This ensures prompts are reproducible, inspectable, and token-efficient.

AIClient Protocol (to be implemented in Commit #6):
    generate_insights(context: AnalysisContext) -> AIInsights
        Given a structured analysis context, return AI-generated insights.

MockAIClient (to be implemented in Commit #6):
    A deterministic implementation that returns realistic-looking stub AIInsights.
    Used in all tests and as the default for the CLI demo.
    Does not call any external service.

Future extension:
    A real AnthropicAIClient can implement the same Protocol without changing
    any other module. The rest of the system is isolated from this choice.
"""

# Implementation will be added in Commit #6.
