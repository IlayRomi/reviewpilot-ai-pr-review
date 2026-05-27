# ReviewPilot

> AI-assisted PR review and test planning — for engineering teams who want faster, more consistent code reviews.

## What it does

ReviewPilot analyzes a local git diff file and generates a structured Markdown report that:

1. **Summarizes** what changed (files, lines added/deleted, file roles)
2. **Identifies** deterministic risk signals (large changes, migrations, auth-touching code, missing tests)
3. **Suggests** likely regression areas *(AI-assisted)*
4. **Proposes** unit, integration, and manual tests *(AI-assisted)*
5. **Produces** a reviewer checklist *(AI-assisted)*

## Design principle

ReviewPilot is **not** a naive "send the whole diff to an LLM and trust the answer" tool.

The system separates two concerns with a hard boundary:

| Layer | What it does | Testable without LLM? |
|---|---|---|
| **Deterministic** | Diff parsing, file classification, risk scoring | ✅ Fully unit-testable |
| **AI-assisted** | Regression hypotheses, test suggestions, reviewer checklist | ✅ Via `MockAIClient` |

The AI layer never receives raw diff text. It receives a structured `AnalysisContext`
(classified file list, risk scores, detected patterns), making prompts reproducible
and inspectable.

## MVP Scope

| Feature | Status |
|---|---|
| Local `.diff` files as input | ✅ In scope |
| Unified diff format (`git diff` output) | ✅ In scope |
| Deterministic risk scoring | ✅ In scope |
| Mock AI client (offline, no API key needed) | ✅ In scope |
| Markdown report output | ✅ In scope |
| GitHub / GitLab API integration | ❌ Out of scope |
| Real Anthropic API | ❌ Out of scope (interface ready) |
| Web UI | ❌ Out of scope |

## Project structure

```
reviewpilot/
├── reviewpilot/          # Main package
│   ├── models.py         # All typed data models
│   ├── parser.py         # .diff → List[DiffFile]
│   ├── classifier.py     # file path → FileRole
│   ├── risk_scorer.py    # DiffFile → RiskScore (deterministic)
│   ├── ai_client.py      # AIClient protocol + MockAIClient
│   ├── report_builder.py # Orchestrates the full pipeline
│   ├── renderer.py       # ReviewReport → Markdown string
│   └── cli.py            # argparse entry point
├── tests/                # pytest test suite
│   └── fixtures/         # Sample .diff files for tests
├── examples/             # Human-readable sample diffs
├── reports/              # Sample generated reports
└── dev_log.md            # Prompt iterations and engineering decisions
```

## Installation

```bash
# Create and activate a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# Install in editable mode with dev dependencies
pip install -e ".[dev]"
```

## Usage

```bash
# Output report to stdout
python -m reviewpilot examples/simple_bugfix.diff

# Write report to a file
python -m reviewpilot examples/simple_bugfix.diff --output reports/my_report.md
```

## Running tests

```bash
# Run all tests
pytest

# Verbose output
pytest -v

# With coverage report
pytest --cov=reviewpilot --cov-report=term-missing
```

## Development log

See [`dev_log.md`](dev_log.md) for a full record of prompt iterations, architectural
decisions, and engineering reflections.

## License

MIT
