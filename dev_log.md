# ReviewPilot — Development Log

This log documents prompt iterations, architectural decisions, issues encountered,
and reflections at each stage of development. It is part of the project deliverable
for the AI Specialist Engineer assignment.

---

## Iteration 1: Planning (2026-05-27)

### Context

Started the project from a blank slate. Before writing any code, worked through a
full planning phase with Claude Code to define scope, architecture, data models,
risk scoring rules, testing strategy, and implementation order.

### What was decided

**Problem statement:** Engineering teams slow down during code review because
reviewers must simultaneously understand what changed, why it might break, and
what to test — with no tooling support. ReviewPilot generates a structured report
to pre-answer those questions.

**MVP scope:** Local `.diff` files only, mock AI client, argparse CLI, Markdown output.
No GitHub API, no real Anthropic API calls, no web UI.

**Architecture:** Three-layer pipeline.
1. Deterministic layer: `parser` → `classifier` → `risk_scorer`
2. AI layer: `ai_client` (protocol + mock)
3. Assembly layer: `report_builder` → `renderer`

**CLI:** `argparse` (stdlib only, no extra dependencies).

**Python version:** 3.11+ (modern typing).

### Key architectural decision: Separate deterministic from AI-assisted analysis

**Decision:** The system uses a hard boundary between deterministic logic and the
AI layer. The AI client never receives raw diff text — it receives a structured
`AnalysisContext` object containing classified files, risk scores, and detected
keyword patterns.

**Rationale:**

1. **Testability.** Deterministic logic (parser, classifier, risk scorer) can be
   fully unit-tested with fixture `.diff` files and known expected outputs. No mocking
   of LLM behavior required for the core analysis. A test can assert
   "this migration file with 300 lines changed scores CRITICAL risk" with complete
   determinism.

2. **Reliability.** The tool produces useful, trustworthy output even if the AI
   layer is unavailable, wrong, or rate-limited. The risk scores and file classifications
   stand alone as engineering artifacts.

3. **Epistemic honesty.** AI-generated sections in the report are explicitly labeled
   as such. A reviewer knows what was computed (deterministic facts) versus what was
   suggested (LLM inference). This prevents false confidence in AI output.

4. **Better prompt engineering.** Sending structured context (a typed `AnalysisContext`)
   rather than a raw 500-line diff gives the LLM a cleaner, smaller working set.
   It also makes prompts easier to iterate on and caps token usage. Structured input
   produces more consistent, evaluable output.

5. **Swappable AI backend.** Because the AI layer sits behind a `Protocol`, the mock
   can be replaced with a real Anthropic SDK client later without touching any other
   module. The rest of the system doesn't care.

### Assumptions made

- Unified diff format only (output of `git diff` or `git format-patch`).
- Single `.diff` file as input per invocation.
- Risk scoring weights are hardcoded constants (extractable to config later).
- No configuration file in MVP.

### Commit created

`scaffold: project structure, empty modules, smoke test, pyproject.toml`

### Next step

**Iteration 2:** Implement data models in `models.py`. Define all dataclasses
before writing any logic — this forces explicit thinking about data flow through
the pipeline.

---

<!-- Add future iterations below this line -->
