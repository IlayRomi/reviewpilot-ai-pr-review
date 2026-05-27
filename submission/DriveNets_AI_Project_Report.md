# ReviewPilot — AI PR Review & Test Planner

**Assignment:** AI Specialist Engineer — DriveNets  
**Candidate:** IlayRomi  
**Date:** May 2026  
**Repository:** TODO  
**Demo recording:** TODO

---

## 1. Executive Summary

Code review is a quality gate, but reviewers consistently face the same problem: a
large, multi-file diff arrives with no signal about where to focus. ReviewPilot is a
command-line tool I built to address this directly.

**What it does.** Given a unified diff file (the output of `git diff`), ReviewPilot:

1. Parses the diff into structured data objects
2. Classifies each changed file by role (source, test, migration, config, infra, docs)
3. Computes deterministic, weighted risk scores based on transparent signal rules
4. Builds a structured `AnalysisContext` — a compact summary passed to the AI layer
5. Generates AI-assisted regression hypotheses, test suggestions, and a reviewer
   checklist via `MockAIClient`
6. Renders a complete Markdown report with every section clearly labeled as either
   *computed deterministically* or *AI-generated*

**Architecture summary.** The system has a hard boundary between deterministic analysis
and the AI layer. The AI client never receives raw diff text — only a structured
`AnalysisContext` object. This keeps the core analysis fully unit-testable and the AI
output grounded in verified data.

**Current status.** The project is a complete, working MVP:

- CLI entry point (`python -m reviewpilot`)
- Four realistic example diffs under `examples/`
- Pre-generated sample report at `reports/sample_report.md`
- 451 passing tests, all offline, no real API calls
- Full documentation in `README.md` and `dev_log.md`

The current implementation uses `MockAIClient` — a deterministic offline stub that
satisfies the `AIClient` Protocol. The interface is ready for a real Anthropic SDK
client without changes to any other module.

---

## 2. Problem Statement

Engineering teams review code continuously, but the review process gives reviewers
almost no structured support. A reviewer opening a large PR must simultaneously
answer four questions with no tooling help:

1. **What changed?** Which files, which roles, how many lines?
2. **Where is the risk?** Which changes are likely to introduce regressions?
3. **What should be tested?** What test gaps does this diff create?
4. **What should I verify manually?** What specific things should I look at?

The obvious response — send the raw diff to an LLM — solves none of these problems
reliably:

- **Untestable.** LLM output is non-deterministic. You cannot write a unit test that
  asserts "this migration file should score CRITICAL risk" when the scoring is inside
  a language model.
- **Opaque.** When the LLM flags a file as risky, it cannot explain *which* signal
  triggered that assessment in a verifiable way.
- **Ungrounded.** An LLM reading a raw diff may hallucinate behavior, reference
  non-existent functions, or generate suggestions unrelated to the actual changes.
- **Not auditable.** If the report says "this auth change may break permissions,"
  there is no way to check whether that came from a real signal in the diff or from
  the model's prior training data.

ReviewPilot is designed around these constraints: run deterministic analysis first,
produce an inspectable intermediate representation, and only then pass structured
context to the AI layer.

---

## 3. Solution Overview

ReviewPilot separates the review pipeline into two clearly defined layers.

**Deterministic layer** — runs without any LLM. Produces verifiable, testable output.

**AI-assisted layer** — receives only structured context, never raw text. Produces
labeled suggestions that reviewers can validate.

### Pipeline

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
  │                               (all_roles passed for cross-file signals)
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
  │
  ▼
stdout or --output file
```

### Report structure

Every generated report contains eight sections in this order:

1. Title and generation timestamp
2. Executive Summary (totals and detected patterns)
3. Changed Files (Markdown table)
4. Deterministic Risk Analysis (per-file signal tables) — labeled "computed deterministically"
5. AI-Assisted Regression Hypotheses — labeled "AI-generated"
6. AI-Assisted Test Suggestions — labeled "AI-generated"
7. Human Reviewer Checklist — labeled "AI-generated"
8. Assumptions and Limitations

---

## 4. Architecture and Components

### `models.py` — Data Models

All typed `dataclasses` and `Enum` classes live here: `DiffLine`, `DiffHunk`,
`DiffFile`, `RiskSignal`, `RiskScore`, `FileSummary`, `AnalysisContext`, `AIInsights`,
`ReviewReport`. Enums cover `FileRole`, `RiskLevel`, `ChangeType`, `LineType`.

Defining all models before writing any logic forces explicit thinking about data flow.
This is the first file I read when picking up context after a break.

**Deterministic.** Pure data definitions. Tested via model construction and
property assertions in `test_models.py`.

### `parser.py` — Diff Parser

A line-by-line state machine that converts a unified diff string into
`List[DiffFile]`. Handles modified, added, deleted, and renamed files; multi-hunk
diffs; and binary files. Raises `ValueError` on empty input or input with no
parseable files.

**Deterministic.** Fully unit-tested in `test_parser.py` with inline string fixtures
for every change type and edge case.

### `classifier.py` — File Classifier

Maps a file path to a `FileRole` using priority-ordered pattern matching:
`TEST > MIGRATION > INFRA > CONFIG > DOCS > SOURCE > UNKNOWN`.

The priority order matters. A test file under `src/` must be `TEST`, not `SOURCE`.
A `docker-compose.yml` is `INFRA`, not `CONFIG`, even though it has a `.yml`
extension. Explicit priority removes the need for special cases.

**Deterministic.** Tested in `test_classifier.py` covering all roles, edge cases,
priority conflicts, and `None` input.

### `risk_scorer.py` — Risk Scorer

Computes a `RiskScore` for each file using nine additive, weighted rules. The score
is the sum of all triggered signal weights, clamped to a minimum of zero.

| Signal | Weight | Fires when |
|---|---:|---|
| `MIGRATION_FILE` | +40 | File role is `MIGRATION` |
| `DESTRUCTIVE_SQL` | +40 | Changed lines contain `drop`, `delete`, `truncate`, or `alter table` |
| `AUTH_SECURITY_KEYWORD` | +35 | Changed lines contain auth/security terms |
| `LARGE_CHANGE` | +30 | File has > 200 changed lines |
| `NO_TEST_COVERAGE` | +20 | `SOURCE` file changed; no `TEST` file anywhere in this diff |
| `INFRA_CHANGE` | +20 | File role is `INFRA` |
| `CONFIG_CHANGE` | +15 | File role is `CONFIG` |
| `TEST_ONLY_CHANGE` | −10 | File role is `TEST` |
| `DOCS_ONLY_CHANGE` | −20 | File role is `DOCS` |

Score to risk level: 0–20 `LOW` · 21–50 `MEDIUM` · 51–80 `HIGH` · 81+ `CRITICAL`

The `NO_TEST_COVERAGE` rule requires `all_roles` (the list of `FileRole` values for
every file in the diff) as a parameter to `score_file()`. This lets the scorer detect
missing test coverage without accessing other files' content directly.

**Deterministic.** Tested in `test_risk_scorer.py` with one test per rule, boundary
conditions, clamping, and cross-file signal logic.

### `ai_client.py` — AI Client Boundary

`AIClient` is a `typing.Protocol` with `@runtime_checkable`. Any class implementing
`generate_insights(context: AnalysisContext) -> AIInsights` satisfies it without
explicit inheritance.

`MockAIClient` is the default implementation. It generates deterministic
`AIInsights` grounded in the `AnalysisContext`: it only references file paths that
exist in the context, never invents symbols, and always produces the same output for
the same input.

**AI-assisted (interface).** The Protocol defines the boundary. `MockAIClient` is
deterministic and fully tested in `test_ai_client.py`. A real Anthropic client drops
in by implementing one method in one new class.

### `report_builder.py` — Pipeline Orchestration

`build_report_from_text()` and `build_report_from_file()` are the two public
functions. They run the full pipeline and return a `ReviewReport`. The raw diff
text string is never forwarded to the AI client — the boundary is enforced here.

**Integration layer.** Tested in `test_report_builder.py` with inline diff fixtures
covering multi-file scenarios, custom titles, custom AI client injection, and error
propagation.

### `renderer.py` — Markdown Renderer

Converts a `ReviewReport` to a Markdown string. Pure presentation: no analysis
logic. `render_markdown()` and `render_to_file()` are the public functions. Pipe
characters in file paths are escaped so Markdown tables do not break.

**Deterministic.** Tested in `test_renderer.py` verifying all eight sections, cell
escaping, trailing newline, and file write behavior.

### `cli.py` and `__main__.py` — Entry Points

`argparse`-based CLI supporting `diff_file` (positional), `--output PATH`,
`--title TITLE`, and `--mock-ai`. Error paths write to `stderr` and exit with
code 1. The `--output` confirmation message also goes to `stderr` so it does not
pollute stdout when output is redirected to a file.

`__main__.py` enables `python -m reviewpilot` in addition to the `reviewpilot`
console script.

**Deterministic.** Tested in `test_cli.py` using `_execute(args)` directly for most
cases and `monkeypatch.setattr(sys, "argv", [...])` for end-to-end tests through
`main()`.

---

## 5. Deterministic vs AI-Assisted Design

| Layer | What it produces | Testable without an LLM? |
|---|---|---|
| **Deterministic** | Diff parsing, file classification, risk signals, report structure | Yes — fully unit-testable |
| **AI-assisted** | Regression hypotheses, test suggestions, reviewer checklist, assumptions | Yes — via `MockAIClient` |

### Why the AI client never receives raw diff text

The `AnalysisContext` object is the only thing the AI client sees. It contains
structured file summaries, risk scores, and detected pattern labels — no raw
diff content.

This decision has four concrete benefits:

1. **Reproducible prompts.** The same diff always produces the same `AnalysisContext`,
   so prompts are stable across runs. This makes the AI layer evaluable.

2. **Inspectable input.** A developer can log or print the `AnalysisContext` and
   verify exactly what the AI was told. With a raw diff, there is no intermediate
   representation to inspect.

3. **Lower leakage risk.** Raw diffs can contain credentials, internal hostnames,
   or proprietary business logic. Sending only extracted metadata reduces the surface
   area of what leaves the local environment.

4. **Swappable backend.** The `AIClient` Protocol is in place. Adding a real
   Anthropic client requires implementing one method (`generate_insights`) in one
   new class. No other module changes.

---

## 6. Claude Code Development Process

I approached the project the same way I would approach a production feature: plan
before coding, implement one module at a time, and verify each step before moving
forward.

### Development workflow

1. **Planning first.** Before writing a single line of code, I asked Claude to
   propose an architecture, define data models, specify risk scoring rules, and
   identify implementation order. The output of that conversation became the
   architecture documented in this report.

2. **One module per commit.** Each commit implemented one module and its tests.
   No commit was made until `pytest` passed cleanly. This kept every intermediate
   state of the repository functional.

3. **Scope enforcement.** I maintained an explicit list of out-of-scope items
   (real API integration, GitHub API, web UI) and refused to expand it mid-session.
   AI assistants tend to suggest improvements; scope creep is a real risk.

4. **Verification before acceptance.** Every Claude-generated file was read before
   being committed. Generated tests were run and their assertions were spot-checked
   for correctness, not just for pass/fail.

5. **Git as a checkpoint system.** Small, focused commits made it easy to identify
   where an issue was introduced and to recover from incorrect AI suggestions without
   losing earlier work.

### Commit progression

| Commit | What was built |
|---|---|
| scaffold | `pyproject.toml`, empty modules, smoke test |
| feat: data models | All `dataclasses` and `Enum` classes |
| feat: diff parser | State machine parser + 89 tests |
| feat: file classifier | Priority-ordered classifier + 178 tests total |
| feat: risk scorer | Nine-rule scorer + 244 tests total |
| feat: AI client | `AIClient` Protocol + `MockAIClient` + 290 tests total |
| feat: report builder | Pipeline orchestration + 350 tests total |
| feat: renderer | Markdown renderer + 415 tests total |
| feat: CLI | Entry points + 451 tests total |
| chore: examples | Four sample diffs + generated report |
| docs: README | Complete usage documentation |
| docs: dev log | Full development log |
| docs: submission | This report |

---

## 7. Prompting Strategy

I did not ask Claude to "build ReviewPilot." I structured each session around a
specific, constrained request with explicit requirements and acceptance criteria.
Below are the five prompt patterns I used throughout the project.

### Pattern 1: Planning prompt

**Goal:** Establish architecture, data models, and implementation order before
writing code.

**Representative excerpt:**
> "Before writing any code: propose an architecture for a CLI tool that analyzes
> a local `.diff` file and generates a structured PR review report. Define the data
> models, describe the risk scoring rules, and specify the implementation order.
> Do not start implementing yet."

**Why it worked:** Getting Claude to plan in full before implementing prevented
mid-session scope changes and produced a stable contract between modules that I
could verify upfront.

### Pattern 2: Module implementation prompt

**Goal:** Implement one module at a time with explicit constraints.

**Representative excerpt:**
> "Implement `risk_scorer.py` using the nine rules defined in the planning phase.
> The scorer must accept `all_roles: list[FileRole]` as a parameter so the
> `NO_TEST_COVERAGE` signal can fire cross-file. Score is clamped to a minimum
> of zero. Do not modify any other module."

**Why it worked:** Giving Claude both the contract (what the function must do) and
the constraint (what it must not touch) produced focused, reviewable output.

### Pattern 3: Testing prompt

**Goal:** Generate a test file with comprehensive coverage before running it.

**Representative excerpt:**
> "Create `tests/test_risk_scorer.py`. Cover: one test per rule, boundary conditions
> for each score band (LOW/MEDIUM/HIGH/CRITICAL), the clamping behavior for
> negative scores, and the cross-file `NO_TEST_COVERAGE` signal. Use inline diff
> fixtures, not files on disk."

**Why it worked:** Specifying coverage goals upfront produced tests that were
actually useful, not just tests that passed by checking trivial properties.

### Pattern 4: Failure-analysis prompt

**Goal:** Diagnose a test failure before changing code.

**Representative excerpt:**
> "One test is failing: `test_context_lines_have_correct_type` expects 3 context
> lines but the parser returns 2. Before changing the parser, analyze whether this
> is a parser bug or a test/fixture expectation bug. Explain your reasoning."

**Why it worked:** Asking Claude to explain before fixing prevented the wrong fix
(weakening the parser) from being applied. The actual root cause was a malformed
fixture.

### Pattern 5: Documentation prompt

**Goal:** Write professional documentation that reflects actual engineering decisions.

**Representative excerpt:**
> "Write `README.md` for a recruiter or engineer reviewing this project. Explain
> what the tool does, why the deterministic/AI boundary exists, and what remains
> out of scope. Tone: professional, not apologetic. Do not claim real LLM
> integration or production readiness."

**Why it worked:** Documentation with an explicit audience and a stated tone
produced output I could use with minimal revision.

### What I controlled directly

I retained ownership of:

- The overall scope and the explicit out-of-scope list
- The decision to use `MockAIClient` throughout the MVP
- The architecture of the `AnalysisContext` boundary
- The exact signal weights and thresholds for risk scoring
- Which failing tests required a code fix vs. a fixture fix
- The commit structure and the content of commit messages
- Verification that every test assertion was actually checking something meaningful

---

## 8. Testing Strategy

### Levels

**Unit tests per module.** Each of `parser`, `classifier`, `risk_scorer`, `ai_client`,
`report_builder`, and `renderer` has its own `tests/test_<module>.py` with focused,
isolated tests. All diff content is inline string fixtures — no external files required.

**Integration tests.** `test_report_builder.py` and `test_renderer.py` test the
assembled pipeline end-to-end using `build_report_from_text()` with inline diffs.
These verify that modules compose correctly.

**CLI tests.** `test_cli.py` calls `_execute(args)` directly (bypassing `argparse`)
for the majority of cases, and patches `sys.argv` via `monkeypatch` for end-to-end
tests through `main()`. `capsys` captures stdout/stderr; `tmp_path` provides
isolated temporary directories for file-output tests.

**Smoke test.** `test_smoke.py` verifies that the package imports without error and
the console script entry point is callable.

### Why MockAIClient in all tests?

`MockAIClient` produces deterministic output: the same `AnalysisContext` always
produces the same `AIInsights`. This makes AI-touching tests reliable and
reproducible. A real API client would introduce network dependency, response
variability, and token cost into every test run. `MockAIClient` eliminates all
three without sacrificing coverage of the pipeline logic.

### Milestone progression

| Stage | Tests passing | Notes |
|---|---:|---|
| Parser | 89 | After fixing one malformed fixture |
| Classifier | 178 | — |
| Risk scorer | 244 | — |
| AI client | 290 | — |
| Report builder | 350 | — |
| Renderer | 415 | — |
| CLI + final project | 451 | All modules, all levels |

---

## 9. Example of AI Output I Evaluated and Corrected

### The parser fixture bug

After Claude generated `test_parser.py`, one test failed:

```
FAILED tests/test_parser.py::TestDiffLineTypes::test_context_lines_have_correct_type
AssertionError: assert 2 == 3  (context line count)
```

The immediate instinct would be to modify the parser to accept both `""` and `" "`
as context lines. I did not do that.

Instead, I asked Claude to explain whether this was a parser bug or a fixture bug
before proposing any fix. The analysis:

- A unified diff context line that is blank in the source file must be represented
  as `" "` (a single space) in the diff, not as `""` (an empty string).
- The parser was implementing the spec correctly.
- The test fixture had a bare empty line where a space-prefixed context line was
  required.

**Resolution:** I fixed the fixture. The parser was not changed.

**Why this matters:** If I had accepted the first instinct and weakened the parser
to accept bare empty lines as context, the parser would have silently misclassified
whitespace-only lines in real diffs. The test suite would have passed while the
production behavior became incorrect. Catching this required reading the unified
diff format specification, not just running the test again.

This is the core verification habit I maintained throughout the project: AI-generated
code and AI-generated tests both require review. A passing test is only as valuable
as the correctness of its assertions.

### Other issues caught

**pytest not installed globally.** The first attempt to run `pytest` after the
scaffold commit failed because the system Python did not have pytest. Resolution:
created a `.venv` and installed with `pip install -e ".[dev]"`. This is a setup
issue, not a code issue — but it illustrates that environment assumptions should
always be verified.

**`__main__.py` left untracked.** After committing the CLI module, `git status`
revealed that `reviewpilot/__main__.py` — the entry point for
`python -m reviewpilot` — had not been staged. The commit was amended after staging
the file. `__main__.py` is not imported by any other source file, so it is invisible
to the usual "did I forget something?" check. Running `git status` after committing
is a habit that catches these.

**Long ad-hoc verification commands.** During CLI development, some PowerShell
one-liners used for quick spot-checks became unwieldy and produced truncated or
unreadable output. Resolution: I stopped relying on ad-hoc shell commands and used
`pytest` as the primary verification path throughout. Pytest is structured,
repeatable, and produces clear pass/fail output that scales to hundreds of tests.

---

## 10. Critical Reflection on Claude's Output

### Where Claude was strong

**Boilerplate and structure.** Claude generated well-structured code quickly —
consistent import order, `__all__` conventions where appropriate, docstrings on all
public functions. This is the kind of work that is correct-by-convention and time-
consuming to write manually.

**Test scaffolding.** Given a clear specification of what to cover, Claude produced
test files that were organized, used appropriate fixtures, and covered the specified
cases. The test files required review but not substantial rewriting.

**Documentation.** `README.md` and `dev_log.md` both needed minimal editing after
Claude's initial drafts. Given a tone and an audience, Claude produced professional
documentation that I could adopt and refine.

**Explaining failures.** When asked to diagnose before fixing, Claude consistently
identified the correct root cause. The instinct to modify code rather than fixtures
(in the parser bug) came from the framing of the question, not from Claude's analysis.

### Where I provided judgment that Claude could not

**Scope enforcement.** Claude naturally suggested improvements throughout the session.
A GitHub integration module, a streaming diff reader, a richer CLI flag set — all
reasonable suggestions, all declined. Keeping a project at MVP scope requires active
resistance to scope expansion.

**The deterministic/AI boundary.** The core architectural decision — never pass raw
diff text to the AI client — was a design requirement I stated upfront and maintained
throughout. Claude implemented it correctly once specified, but the requirement itself
came from engineering judgment about testability and auditability, not from a prompt.

**Test assertion quality.** Claude generated tests that passed. I verified that the
assertions were checking the right things. A test that asserts `assert len(results) > 0`
on a list is weaker than one that asserts `assert results[0].label == "AUTH_SECURITY_KEYWORD"`.
Several generated tests were tightened in this way.

**Fixture correctness.** As the parser fixture bug demonstrates, Claude can generate
a test fixture that does not conform to the format the code is designed for. Verifying
fixtures requires understanding the spec, not just running the tests.

**Commit hygiene.** Claude does not track git state. Staging the right files,
writing focused commit messages, and noticing untracked files are all developer
responsibilities that cannot be delegated.

---

## 11. What I Chose Not To Test

Several behaviors were intentionally excluded from the test suite as acceptable MVP
tradeoffs:

**Real LLM output quality.** `MockAIClient` tests the pipeline, not the quality of
actual LLM suggestions. A golden-output evaluation set would be needed to test
real AI responses systematically. This is a known gap, not an oversight.

**Very large diffs.** No performance or memory tests. The tool targets typical PR
sizes (under a few thousand changed lines). Multi-megabyte diffs are not a design
target for this scope.

**Full malformed diff recovery.** The parser handles standard `git diff` output and
raises `ValueError` on empty input. Corrupted, truncated, or non-standard diff
variants are not exhaustively tested. This is acceptable for a tool that is invoked
on locally-generated diffs.

**Runtime behavior of changed application code.** ReviewPilot analyzes the diff. It
cannot verify whether the changed code is correct. This is explicit in the
Assumptions and Limitations section of every generated report.

**Semantic code understanding.** Risk scoring is keyword-based. The scorer does not
parse the AST, trace control flow, or analyze imports. This is a known limitation
that a future version would address with language-aware analysis.

**Cross-platform path handling.** The classifier normalizes backslashes to forward
slashes, but exhaustive cross-platform edge cases are not tested. Development
was done on Windows; the classifier is designed to handle both.

---

## 12. Current Limitations

| Limitation | Description |
|---|---|
| Input format | Local `.diff` files only. No GitHub/GitLab API, no piped input, no live `git diff`. |
| AI backend | `MockAIClient` only. No real LLM output in the current MVP. |
| Risk scoring | Heuristic and keyword-based. No AST, no control-flow analysis, no semantic understanding. |
| Repository context | The tool operates on the diff in isolation. No commit history, no test coverage data, no dependency analysis. |
| Runtime behavior | Changes are not executed. The tool cannot verify whether a change breaks tests or alters runtime behavior. |
| Language coverage | File classification covers common extensions and directories but is not exhaustive for all ecosystems. |
| Output format | Markdown only. No HTML, SARIF, or CI-native formats. |

---

## 13. Future Improvements

**Real Anthropic API client.** The `AIClient` Protocol is already in place. Implementing
`AnthropicAIClient` requires one class with one method. No other module changes are
needed. This is the highest-value next step.

**GitHub PR integration.** Fetch diffs via the GitHub REST API and post the generated
report as a PR comment. The Markdown output format is already suitable. The `AIClient`
swap above would make the posted report use real LLM suggestions.

**Configurable risk rules.** Load signal weights and keyword sets from a project-level
`reviewpilot.toml` file rather than hardcoded constants. Different teams have different
risk profiles; a migration that drops a column may be routine in one codebase and
critical in another.

**Repository-aware context.** Enrich `AnalysisContext` with recent commit history for
touched files, test coverage data for changed lines, and cross-PR change frequency.
This would improve the quality of AI-assisted suggestions without changing the
boundary design.

**Golden output evaluation suite.** Maintain a set of reference diffs with expected
report sections to regression-test the AI layer across model versions. This is the
tooling required to make real LLM output evaluable in CI.

**CI integration.** Run ReviewPilot as a GitHub Actions step on every PR. Post the
report as a comment automatically. This turns the tool from a local utility into
part of the review workflow.

**Richer output formats.** HTML report with collapsible sections, SARIF format for
GitHub Code Scanning integration, or a structured JSON output for downstream tooling.

---

## 14. Demo

### Prerequisites

```bash
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

### Run against the example diffs

```bash
# High-risk auth change: AUTH_SECURITY_KEYWORD + NO_TEST_COVERAGE → HIGH (55)
python -m reviewpilot examples/auth_change.diff

# Critical database migration: MIGRATION_FILE + DESTRUCTIVE_SQL + AUTH_SECURITY_KEYWORD → CRITICAL (115)
python -m reviewpilot examples/migration_change.diff

# Low-risk documentation change: DOCS_ONLY_CHANGE → LOW (0)
python -m reviewpilot examples/safe_docs_change.diff

# Source with accompanying tests: NO_TEST_COVERAGE does not fire → LOW (0)
python -m reviewpilot examples/source_with_tests.diff
```

### Generate the sample report

```bash
python -m reviewpilot examples/auth_change.diff --output reports/sample_report.md
```

The generated report is already committed at `reports/sample_report.md`.

### Run the test suite

```bash
python -m pytest tests/ -v
```

Expected result: **451 passed**.

### Repository and recording

- **GitHub repository:** TODO
- **Recorded demo:** TODO

---

## 15. Conclusion

ReviewPilot started from a clear problem statement — code reviewers need structured
risk signal, not raw LLM output — and was built one verified module at a time to
a working, documented, tested state.

The engineering decisions that shaped the project were deliberate and defensible:
separate deterministic from AI-assisted analysis, enforce the boundary with a typed
intermediate object, keep the AI backend behind a Protocol so it can be swapped
without touching any other module, and test every layer offline with a deterministic
mock. These are not shortcuts — they are the decisions that make the tool reliable
and the codebase maintainable.

Using Claude Code as an implementation assistant accelerated the scaffolding,
testing, and documentation phases meaningfully. It did not replace engineering
judgment. The architecture was designed before any code was generated. Failures were
diagnosed before they were fixed. Every output was verified before it was committed.

This project demonstrates how I approach AI-assisted engineering: Claude is a
capable collaborator for well-constrained tasks, a strong test-writer when given
clear coverage goals, and an effective documentation author when given an audience
and a tone. The developer's role is to define the constraints, verify the outputs,
and hold the line on quality — not to accept everything that compiles.

---

*ReviewPilot — developed as the AI Specialist Engineer assignment for DriveNets, May 2026.*
