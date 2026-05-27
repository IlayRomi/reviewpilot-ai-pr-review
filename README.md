# ReviewPilot

**ReviewPilot** is an AI-assisted PR review and test-planning CLI that analyzes git diffs and produces structured Markdown review reports.

---

## Why I built this

Code review is a quality gate, but reviewers face a consistent problem: a large, multi-file diff lands in their queue with no signal about *where to focus*. Which file is a high-risk schema migration? Which auth change deserves a security deep-dive? Which test gaps should be flagged before merging?

AI can help answer these questions — but only if it is asked the right questions. A tool that blindly forwards raw diffs to an LLM produces inconsistent, ungrounded output. ReviewPilot takes a different approach:

1. **Deterministic analysis first.** Parse the diff, classify each file by role, and compute risk scores using transparent, rule-based heuristics. No LLM involved.
2. **Structured AI input.** Pass only a compact `AnalysisContext` (file roles, risk scores, detected patterns) to the AI layer — never raw diff text. This keeps prompts reproducible, token-efficient, and auditable.
3. **Clearly labeled output.** Every section of the report is explicitly marked as either *computed deterministically* or *AI-generated*. Reviewers always know what to trust and what to validate.

This design reflects a deliberate engineering judgment: use AI where it adds value (hypothesis generation, test suggestion) and keep the critical analysis layer fully testable and explainable.

---

## What it does

Given a unified diff file (output of `git diff`), ReviewPilot:

1. **Parses** the diff into structured `DiffFile` objects (hunks, lines added/removed, change type)
2. **Classifies** each changed file by role: `SOURCE`, `TEST`, `CONFIG`, `MIGRATION`, `INFRA`, `DOCS`, or `UNKNOWN`
3. **Scores** each file using additive, weighted risk signals (auth keywords, large changes, missing tests, destructive SQL, etc.)
4. **Generates** AI-assisted regression hypotheses, test suggestions, and a reviewer checklist via the `MockAIClient`
5. **Renders** a complete Markdown report with all sections clearly separated and labeled

---

## Quick demo

```bash
# Install dependencies
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"

# Run against the auth example diff
python -m reviewpilot examples/auth_change.diff --output reports/sample_report.md
```

The report is written to `reports/sample_report.md`. To preview in the terminal:

```bash
python -m reviewpilot examples/auth_change.diff
```

---

## Example output

A pre-generated report is available at [`reports/sample_report.md`](reports/sample_report.md).

It was produced from [`examples/auth_change.diff`](examples/auth_change.diff) and demonstrates:

- the Changed Files table with roles, line counts, risk levels, and scores
- the Deterministic Risk Analysis section with triggered signal labels, weights, and reasons
- AI-assisted regression hypotheses referencing the specific high-risk file
- auth/security-targeted test suggestions
- a reviewer checklist with actionable checkbox items
- assumptions and limitations clearly noted

---

## Architecture

```
.diff file
  │
  ▼
parser.parse_diff_text()        — unified diff → List[DiffFile]
  │
  ▼
classifier.classify_file()      — file path → FileRole (per file)
  │
  ▼
risk_scorer.score_file()        — DiffFile + FileRole → RiskScore
  │                               (uses all_roles for cross-file signals)
  ▼
AnalysisContext                 — structured summary, no raw diff text
  │
  ▼
MockAIClient.generate_insights()  — context → AIInsights
  │
  ▼
ReviewReport                    — fully assembled data object
  │
  ▼
renderer.render_markdown()      — ReviewReport → Markdown string
```

**Module responsibilities:**

| Module | Responsibility |
|---|---|
| `models.py` | All typed dataclasses and enums (`DiffFile`, `RiskScore`, `ReviewReport`, …) |
| `parser.py` | State-machine diff parser; raises `ValueError` on empty or unparseable input |
| `classifier.py` | Priority-ordered path pattern matching (TEST > MIGRATION > INFRA > CONFIG > DOCS > SOURCE) |
| `risk_scorer.py` | Additive weighted signals; score clamped to ≥ 0; transparent `RiskSignal` list |
| `ai_client.py` | `AIClient` Protocol + `MockAIClient`; real clients drop in without touching other modules |
| `report_builder.py` | Pipeline orchestration; enforces the AI boundary (no raw text to AI layer) |
| `renderer.py` | Pure presentation; converts `ReviewReport` → Markdown string |
| `cli.py` | `argparse` entry point; no business logic |

---

## Deterministic vs AI-assisted

| Layer | What it produces | Testable without an LLM? |
|---|---|---|
| **Deterministic** | Diff parsing, file classification, risk signals, report structure | ✅ Fully unit-testable |
| **AI-assisted** | Regression hypotheses, test suggestions, reviewer checklist, assumptions | ✅ Via `MockAIClient` |

The AI layer receives an `AnalysisContext` containing file summaries, risk scores, and detected patterns. **It never receives raw diff text.** This makes the AI boundary inspectable, the prompts reproducible, and the full pipeline testable offline.

### Risk signal weights

| Signal | Weight | Fires when |
|---|---:|---|
| `MIGRATION_FILE` | +40 | File role is `MIGRATION` |
| `DESTRUCTIVE_SQL` | +40 | Changed lines contain `drop`, `delete`, `truncate`, or `alter table` |
| `AUTH_SECURITY_KEYWORD` | +35 | Changed lines contain auth/security terms (`token`, `secret`, `jwt`, `credential`, …) |
| `LARGE_CHANGE` | +30 | File has > 200 changed lines |
| `NO_TEST_COVERAGE` | +20 | `SOURCE` file changed with no `TEST` file in the same diff |
| `INFRA_CHANGE` | +20 | File role is `INFRA` |
| `CONFIG_CHANGE` | +15 | File role is `CONFIG` |
| `TEST_ONLY_CHANGE` | −10 | File role is `TEST` |
| `DOCS_ONLY_CHANGE` | −20 | File role is `DOCS` |

Score → risk level: 0–20 `LOW` · 21–50 `MEDIUM` · 51–80 `HIGH` · 81+ `CRITICAL`

---

## Installation

```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Requires **Python 3.11+**. No runtime dependencies beyond the standard library. `pytest` and `pytest-cov` are installed by `[dev]`.

---

## Usage

```bash
# Print report to stdout
python -m reviewpilot examples/auth_change.diff

# Write report to a file
python -m reviewpilot examples/auth_change.diff --output reports/sample_report.md

# Use a custom report title
python -m reviewpilot examples/auth_change.diff --title "Auth PR Review"

# All options together
python -m reviewpilot examples/migration_change.diff \
  --title "Sprint 42 — DB Migration" \
  --output reports/migration_review.md
```

```
usage: reviewpilot [-h] [--output PATH] [--title TITLE] [--mock-ai] diff_file

positional arguments:
  diff_file       Path to a unified diff file (output of git diff)

options:
  --output PATH   Write report to a file instead of stdout
  --title TITLE   Custom report title
  --mock-ai       Force MockAIClient (always active in current MVP)
  -h, --help      Show this help message and exit
```

---

## Running tests

```bash
# Run the full test suite
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=reviewpilot --cov-report=term-missing
```

**451 tests passing** at the time of this commit, covering all modules end-to-end with no real API calls. The test suite is intentionally fast — it runs entirely offline using `MockAIClient`.

---

## Sample scenarios

Four realistic example diffs are included under `examples/`:

| File | Scenario | Expected risk |
|---|---|---|
| `auth_change.diff` | Auth module refactor — removes hardcoded secrets, updates token validation and permission checks | **HIGH** (55): `AUTH_SECURITY_KEYWORD` + `NO_TEST_COVERAGE` |
| `migration_change.diff` | Database migration — `DROP TABLE`, `ALTER TABLE`, `TRUNCATE` on permission tables | **CRITICAL** (115): `MIGRATION_FILE` + `DESTRUCTIVE_SQL` + `AUTH_SECURITY_KEYWORD` |
| `safe_docs_change.diff` | Documentation update — rewrites `## Installation` section in `docs/usage.md` | **LOW** (0): `DOCS_ONLY_CHANGE` reduces score, clamped to 0 |
| `source_with_tests.diff` | Pricing logic refactor with accompanying tests — `src/pricing.py` + `tests/test_pricing.py` | **LOW** (0): `NO_TEST_COVERAGE` does **not** fire because a test file is present in the diff |

To run ReviewPilot against all examples:

```bash
python -m reviewpilot examples/auth_change.diff
python -m reviewpilot examples/migration_change.diff
python -m reviewpilot examples/safe_docs_change.diff
python -m reviewpilot examples/source_with_tests.diff
```

---

## Testing strategy

The test suite covers three levels:

1. **Unit tests per module** — each of `parser`, `classifier`, `risk_scorer`, `ai_client`, `report_builder`, and `renderer` has its own `tests/test_<module>.py` with focused, isolated tests
2. **Integration tests** — `test_report_builder.py` and `test_renderer.py` test the assembled pipeline end-to-end using inline diff fixtures
3. **CLI tests** — `test_cli.py` covers argument parsing, stdout/file output, error handling, and exit codes using `monkeypatch` and `capsys`
4. **Smoke test** — `test_smoke.py` verifies the package imports and console script entry point

All tests use `MockAIClient` — no API keys, no network calls, no non-determinism.

---

## Project structure

```
reviewpilot/
├── reviewpilot/          # Main package
│   ├── __init__.py       # Version and author
│   ├── __main__.py       # python -m reviewpilot entry point
│   ├── models.py         # All typed dataclasses and enums
│   ├── parser.py         # .diff → List[DiffFile]
│   ├── classifier.py     # file path → FileRole
│   ├── risk_scorer.py    # DiffFile + role → RiskScore (deterministic)
│   ├── ai_client.py      # AIClient Protocol + MockAIClient
│   ├── report_builder.py # Orchestrates the full analysis pipeline
│   ├── renderer.py       # ReviewReport → Markdown string
│   └── cli.py            # argparse entry point
├── tests/                # pytest test suite (451 tests, all offline)
├── examples/             # Realistic sample .diff files
├── reports/              # Pre-generated sample Markdown report
├── dev_log.md            # Prompt iteration notes and engineering decisions
└── CLAUDE.md             # Claude Code session instructions
```

---

## Current limitations

- **Input format:** local `.diff` files only — no GitHub/GitLab API integration, no live `git diff` pipe
- **AI backend:** `MockAIClient` only — suggestions are deterministic mock output, not real LLM output
- **Risk scoring:** heuristic, keyword-based — no semantic code analysis or control-flow understanding
- **Scope:** single diff in isolation — no repository history, no cross-PR context, no test coverage metrics
- **Runtime behavior:** not verified — the tool cannot detect whether changes break existing tests or alter runtime behavior
- **Language support:** file classification covers common extensions but is not exhaustive

---

## Future improvements

The `AIClient` Protocol is already in place. Swapping `MockAIClient` for a real backend requires implementing one method (`generate_insights`) in a new class — no other module needs to change.

Planned extensions (not in MVP):

- **Real Anthropic API client** — implement `AnthropicAIClient` behind the existing `AIClient` Protocol
- **GitHub PR integration** — fetch diffs and post reports as PR comments via the GitHub API
- **Configurable risk rules** — load signal weights and keyword sets from a project-level config file
- **Repository-aware context** — include recent commit history and test coverage data in `AnalysisContext`
- **Golden output evaluation** — maintain a set of reference diffs with expected report outputs for regression testing the AI layer
- **CI integration** — run ReviewPilot as a GitHub Actions step on every PR
- **Richer report formats** — HTML output, SARIF format for tool integrations

---

## Development log

See [`dev_log.md`](dev_log.md) for a full record of architectural decisions, prompt iterations, and engineering reflections across all implementation commits.

---

## License

MIT
