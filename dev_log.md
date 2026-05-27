# ReviewPilot — Development Log

This log documents design decisions, prompt strategies, issues encountered, and
engineering reflections at each stage of development. It is part of the project
deliverable for the AI Specialist Engineer hiring assignment.

---

## Project Context

**Assignment goal:** Demonstrate AI-assisted engineering judgment by building a
small but complete tool that uses LLMs thoughtfully — not as a black box.

**Tool chosen:** ReviewPilot — a CLI that analyzes a git diff file and produces
a structured Markdown PR review report with deterministic risk analysis and
AI-assisted suggestions.

**Development approach:** Plan first, then implement one module at a time. Each
commit leaves `pytest` passing. Claude Code was used throughout as the AI
implementation assistant; all outputs were reviewed, verified, and corrected
where necessary before committing.

---

## Design Principles

These principles were established before any code was written and held throughout
all implementation commits:

1. **Deterministic before AI.** The core analysis — diff parsing, file classification,
   risk scoring — runs entirely without an LLM. The AI layer receives structured
   context, never raw diff text.

2. **Hard AI boundary.** The `AnalysisContext` object is the only thing passed to
   the AI client. This keeps prompts token-efficient, reproducible, and free of
   accidental data leakage.

3. **Epistemic honesty.** Every AI-generated section of the report is explicitly
   labeled so reviewers know what was computed vs. what was suggested.

4. **Test every module.** No module is committed without a corresponding test file.
   All tests use `MockAIClient` — no network calls, no API keys, no non-determinism.

5. **MockAIClient by default.** A real Anthropic API client was explicitly deferred.
   The `AIClient` Protocol is ready; the mock satisfies it. This decision keeps the
   tool fully offline-testable and avoids coupling the test suite to an external service.

---

## Development Timeline

| Iteration | What was built | Tests after commit |
|---|---|---|
| 0 | Project selection and framing | — |
| 1 | Planning (architecture, scope, data flow) | — |
| 2 | Project scaffold (pyproject.toml, empty modules, smoke test) | — |
| 3 | Data models (`models.py`) | — |
| 4 | Diff parser (`parser.py`) + fixture bug fix | 89 passed |
| 5 | File classifier (`classifier.py`) | 178 passed |
| 6 | Deterministic risk scorer (`risk_scorer.py`) | 244 passed |
| 7 | AI client boundary + MockAIClient (`ai_client.py`) | 290 passed |
| 8 | Report builder (`report_builder.py`) | 350 passed |
| 9 | Markdown renderer (`renderer.py`) | 415 passed |
| 10 | CLI entry point (`cli.py`, `__main__.py`) | 451 passed |
| 11 | Sample diffs + generated sample report | 451 passed |
| 12 | README polish and usage documentation | 451 passed |

---

## Iteration 0 — Project Selection and Framing

### Goal

Choose a project scope that is small enough to complete in a single focused session,
concrete enough to demonstrate real engineering judgment, and interesting enough
to showcase AI-assisted analysis rather than just AI-generated text.

### Framing decision

Several project ideas were considered. A "send the whole diff to an LLM and return
the response" tool was explicitly rejected — that demonstrates prompt construction
but not engineering judgment. ReviewPilot was chosen because it requires:

- a real parsing problem (unified diff format)
- a classification and scoring layer that must be independently testable
- a deliberate AI boundary with a clear rationale
- a rendering layer that separates presentation from logic
- a proper CLI with error handling

This framing makes the project evaluable at multiple levels: the code, the tests,
the architecture, and the reasoning behind each decision.

---

## Iteration 1 — Planning with Claude Code

### Prompt strategy

Asked Claude Code to work in planning mode before writing any code: define the
problem, propose an architecture, design the data models, specify risk scoring
rules, and outline an implementation order. The goal was to think through the
full system before touching a file.

### What was decided

**Architecture:** Three-layer pipeline.
1. Deterministic layer: `parser` → `classifier` → `risk_scorer`
2. AI boundary: `AnalysisContext` (structured context object, never raw text)
3. Assembly layer: `report_builder` → `renderer` → CLI

**Data models:** All as typed `dataclasses` (`DiffFile`, `DiffHunk`, `DiffLine`,
`RiskScore`, `RiskSignal`, `FileSummary`, `AnalysisContext`, `AIInsights`, `ReviewReport`).
Enums for `FileRole`, `RiskLevel`, `ChangeType`, `LineType`.

**Risk signals and weights:** Nine rules defined upfront with explicit integer weights,
ranging from +40 (migration, destructive SQL) down to −20 (docs-only change).

**AI client design:** `AIClient` as a `typing.Protocol` with `@runtime_checkable`.
`MockAIClient` as the default for all offline use and testing.

**Implementation order:** one module per commit, models first, CLI last.

### Key judgment call: why not use a real LLM API?

The `AIClient` Protocol is ready. Wiring a real Anthropic client requires
implementing one method (`generate_insights`) in one new class. The deliberate
choice to defer it was not a capability gap — it was an architectural boundary.

Coupling the test suite to a live API would introduce:
- non-determinism (outputs change across runs)
- test fragility (network failures, rate limits, API key management)
- cost (API calls on every `pytest` run)

`MockAIClient` is grounded in the `AnalysisContext` — it only references file paths
that exist in the context, produces deterministic output, and exercises the full
pipeline without these downsides. The real backend drops in later without touching
any other module.

### Assumptions made

- Unified diff format only (output of `git diff`).
- Single `.diff` file as input per invocation.
- Risk scoring weights are hardcoded constants (extractable to config later).
- No web UI, no GitHub API, no configuration file in MVP.

---

## Iteration 2 — Project Scaffold

### What was built

`pyproject.toml`, `reviewpilot/__init__.py`, empty module stubs with docstrings,
and `tests/test_smoke.py` (verifies the package imports and entry point).

### Prompt strategy

Gave Claude the exact MVP scope, architecture, and module list. Asked for scaffold
only — no business logic. Verified that `pytest` ran the smoke test before committing.

### Environment issue: pytest not installed globally

After generating the scaffold, the initial `pytest` invocation failed because
`pytest` was not installed globally in the development environment. Resolution:
created a `.venv`, installed dev dependencies with `pip install -e ".[dev]"`,
and ran all subsequent tests inside the virtual environment.

**Takeaway:** Always verify the test runner works before building on top of it.

---

## Iteration 3 — Data Models

### What was built

All typed `dataclasses` and `Enum` classes in `reviewpilot/models.py`.

### Prompt strategy

Asked Claude to implement models exactly matching the architecture decision from
Iteration 1. Verified three properties specifically: all list fields use
`default_factory=list`, `DiffFile.display_path` returns the correct fallback chain
(`new_path or old_path or "<unknown>"`), and `DiffFile.total_changes` is computed
as `additions + deletions`.

### Judgment call: dataclasses over Pydantic

`dataclasses` from the standard library were used throughout. Pydantic would add
validation and serialization, but the MVP has no serialization requirement and no
external input to validate — the diff parser constructs all model instances directly.
Adding Pydantic would be a dependency with no concrete benefit at this scope.

---

## Iteration 4 — Diff Parser

### What was built

`reviewpilot/parser.py` — a line-by-line state machine that parses unified diff
format into `list[DiffFile]`. `tests/test_parser.py` with 89 tests covering
modified, added, deleted, and renamed files, multi-hunk diffs, and error cases.

### Prompt strategy

Provided the full unified diff format specification and asked for a state machine
implementation. Specified exact error cases: empty input, no parseable files.
Asked for test fixtures as inline string constants (not files on disk) to keep
the test suite self-contained.

### Issue caught: parser fixture bug

One test failed after initial implementation:

```
FAILED tests/test_parser.py::TestDiffLineTypes::test_context_lines_have_correct_type
```

The test asserted 3 context lines but the parser returned 2. Before modifying the
parser, the issue was analyzed:

- The parser was correct: unified diff context lines **must** start with a single
  space character (`" "`). An empty context line in the diff must be `" "` (space),
  not `""` (empty string).
- The fixture had a bare empty line `""` where a space-prefixed context line
  `" "` was required.

**Resolution:** Fixed the fixture, not the parser. The test passed after the
correction.

**Why this matters:** This is a concrete example of verifying AI-generated test code
before trusting it. The failure looked like a parser bug but was actually a fixture
that didn't conform to the format the parser was designed for. Changing the parser
to accept bare empty lines as context would have introduced incorrect behavior.

### Verification result

89 tests passing after the fixture fix.

---

## Iteration 5 — File Classifier

### What was built

`reviewpilot/classifier.py` — priority-ordered path pattern matching returning
`FileRole`. `tests/test_classifier.py` with 89 new tests (178 total).

### Prompt strategy

Specified the exact priority order: `TEST > MIGRATION > INFRA > CONFIG > DOCS > SOURCE > UNKNOWN`.
Provided specific cases that would be ambiguous without explicit priority: a test
file under `src/`, a `docker-compose.yml` that is both INFRA and CONFIG by extension,
a `.py` file in a `migrations/` directory.

### Key design decision: INFRA before CONFIG

`docker-compose.yml` has a `.yml` extension, which matches CONFIG patterns. But it
is semantically an infrastructure file. By placing INFRA before CONFIG in the
priority order, the classifier correctly returns `INFRA` without special-casing this
file. The rule is general: infrastructure files that also match config patterns are
classified as INFRA.

### Verification result

178 tests passing.

---

## Iteration 6 — Deterministic Risk Scoring

### What was built

`reviewpilot/risk_scorer.py` — nine additive rules producing `RiskScore` with
`RiskSignal` list. Score clamped to minimum 0. `tests/test_risk_scorer.py` with
66 new tests (244 total).

### Prompt strategy

Provided the full rule specification from the planning phase. Asked explicitly for
`all_roles` as a parameter to `score_file()` so the `NO_TEST_COVERAGE` signal could
fire cross-file (when a source file changes but no test file is present in the same
diff). Specified that negative signals (test-only, docs-only) cannot produce a
negative total score.

### Key design decision: cross-file signal via all_roles

`NO_TEST_COVERAGE` cannot be evaluated by looking at a single file in isolation.
It fires when a `SOURCE` file is changed AND no `TEST` file is present anywhere in
the diff. Passing `all_roles: list[FileRole]` to `score_file()` avoids giving the
scorer access to other files' content while still providing the information it needs
to evaluate this cross-file condition.

### Verification result

244 tests passing.

---

## Iteration 7 — AI Client Boundary and MockAIClient

### What was built

`reviewpilot/ai_client.py` — `AIClient` Protocol with `@runtime_checkable` and
`MockAIClient`. The mock generates deterministic insights grounded in the
`AnalysisContext`: it only references file paths that exist in the context, never
invents file names or symbols. `tests/test_ai_client.py` with 46 new tests
(290 total).

### Prompt strategy

Emphasized two invariants:
1. `MockAIClient` must be grounded — every `display_path` referenced in AI output
   must come from `context.file_summaries`.
2. `_build_assumptions()` must always return exactly 3 items regardless of context
   content, so the "assumptions always present" property is easy to test.

### Key design decision: Protocol over ABC

`AIClient` uses `typing.Protocol` rather than `ABC`. This means any class with a
compatible `generate_insights` method satisfies the interface without explicit
inheritance. A real Anthropic client written independently can satisfy `AIClient`
just by implementing the method. The `@runtime_checkable` flag enables
`isinstance(client, AIClient)` checks in tests.

### Verification result

290 tests passing.

---

## Iteration 8 — Report Builder

### What was built

`reviewpilot/report_builder.py` — pipeline orchestration. `build_report_from_text()`
and `build_report_from_file()` as the two public functions. `_extract_detected_patterns()`
returns a sorted list of unique signal labels for inclusion in `AnalysisContext`.
`tests/test_report_builder.py` with 60 new tests (350 total).

### Prompt strategy

Asked Claude to enforce the AI boundary explicitly in the implementation:
`AnalysisContext` is constructed from structured data only; the raw `diff_text`
string is never forwarded to the AI client. Verified this invariant in code review
before accepting the implementation.

### Key design decision: detected_patterns as sorted list

`detected_patterns` in `AnalysisContext` is `sorted(set(...))` rather than a set.
This ensures the field is deterministic across runs (same input → same output) and
makes test assertions straightforward. Sets have non-deterministic iteration order
in Python; a sorted list does not.

### Verification result

350 tests passing.

---

## Iteration 9 — Markdown Renderer

### What was built

`reviewpilot/renderer.py` — pure presentation layer converting `ReviewReport` to
a Markdown string. `render_markdown()` and `render_to_file()` as the public API.
`_esc()` for pipe-character escaping in table cells. `tests/test_renderer.py` with
65 new tests (415 total).

### Prompt strategy

Specified the exact section order and heading strings. Required:
- `✅` badge in the deterministic section
- `⚠️` banner in all AI-generated sections
- `- [ ]` checkbox syntax in the reviewer checklist
- `_esc()` to escape `|` characters in table cells (file paths containing `|`
  would otherwise break Markdown table rendering)
- Output always ends with `"\n"`

### Design decision: _esc() in both table rows and section headings

Pipe characters can appear in file paths (unusual but possible). The escaping
function is applied in both the Changed Files table cells and the per-file `###`
subheadings in the Deterministic Risk Analysis section. This prevents rendering
breakage without requiring the rest of the pipeline to sanitize file paths.

### Verification result

415 tests passing.

---

## Iteration 10 — Command Line Interface

### What was built

`reviewpilot/cli.py` — `argparse` entry point with `main()`, `_build_parser()`,
`_execute()`, and `_die()`. `reviewpilot/__main__.py` for `python -m reviewpilot`
support. `tests/test_cli.py` with 36 new tests (451 total).

### Prompt strategy

Asked for `_execute(args: Namespace)` to be separated from `main()` so it can be
called directly in tests without patching `sys.argv`. Error paths write to `stderr`
and call `sys.exit(1)`. Confirmation of file write goes to `stderr` (not `stdout`)
so it does not pollute report content when stdout is redirected.

### Issue caught: __main__.py left untracked

After the commit, `git status` revealed that `reviewpilot/__main__.py` was not
staged. The entry point for `python -m reviewpilot` was missing from the commit.

**Resolution:** Verified the file existed, staged it, and amended the commit.

**Takeaway:** Always run `git status` after committing to catch untracked files.
`__main__.py` is easy to overlook because it is not referenced by any other source
file — only by Python's module execution mechanism.

### Issue noted: long PowerShell spot-checks

During CLI development, some ad-hoc verification commands in PowerShell were written
as single long lines that exceeded command length limits or produced truncated output.
**Resolution:** Relied on `pytest` as the definitive verification path rather than
PowerShell one-liners. Pytest is deterministic, repeatable, and produces structured
output that is easy to interpret.

### Verification result

451 tests passing.

---

## Iteration 11 — Sample Diffs and Demo Report

### What was built

Four realistic example `.diff` files under `examples/` and a pre-generated
sample report at `reports/sample_report.md`.

### Diff scenarios and expected behavior

| File | Role | Key signals | Risk |
|---|---|---|---|
| `auth_change.diff` | SOURCE | AUTH_SECURITY_KEYWORD (+35), NO_TEST_COVERAGE (+20) | HIGH (55) |
| `migration_change.diff` | MIGRATION | MIGRATION_FILE (+40), DESTRUCTIVE_SQL (+40), AUTH_SECURITY_KEYWORD (+35) | CRITICAL (115) |
| `safe_docs_change.diff` | DOCS | DOCS_ONLY_CHANGE (−20, clamped to 0) | LOW (0) |
| `source_with_tests.diff` | SOURCE + TEST | NO_TEST_COVERAGE does not fire (TEST in all_roles) | LOW (0) |

`migration_change.diff` reaching CRITICAL is a deliberate design demonstration:
a migration that restructures permission tables triggers three independent signals.
The additive scoring model surfaces compound risk that a single rule could not.

`source_with_tests.diff` demonstrates the cross-file `NO_TEST_COVERAGE` logic:
because the diff includes a test file, the source file's risk score does not increase.

### Generating the sample report

The sample report was generated directly via the CLI:

```bash
python -m reviewpilot examples/auth_change.diff --output reports/sample_report.md
```

Output was inspected to verify all eight sections were present, signal labels and
weights were correctly displayed, and the AI-assisted sections referenced the actual
file path from the diff.

### Verification result

451 tests passing (no new tests added; the example diffs are demo artifacts, not
test fixtures).

---

## Iteration 12 — README Polish and Usage Guide

### What was built

A complete `README.md` rewrite covering: project rationale, architecture diagram,
deterministic vs AI-assisted layers, signal weight table, installation, usage
examples, testing summary, all four sample scenarios, testing strategy, limitations,
and future improvements.

### Prompt strategy

Provided a detailed section outline with required content for each section. Specified
tone: professional, not apologetic about MVP scope, emphasizing engineering judgment
rather than feature count.

### Key content decisions

- **Why section before What section.** The design rationale is more interesting to
  a technical reviewer than the feature list. Leading with "why" separates this from
  a typical demo project README.

- **Signal weight table in README.** Including the full signal table makes the
  deterministic layer concrete and reviewable without reading source code.

- **Limitations stated plainly.** Over-claiming capability is worse than honest
  scoping. The limitations section states exactly what the tool does not do:
  no semantic analysis, no repository history, no real LLM output.

- **Future improvements reference the Protocol.** The README notes explicitly that
  adding a real Anthropic client requires implementing one method in one class. This
  makes the architectural decision concrete, not just theoretical.

### Verification result

451 tests passing (no code changes, README only).

---

## Testing Strategy

The test suite has four levels:

### 1. Unit tests per module

Each module has its own `tests/test_<module>.py`. Tests are isolated — no real
filesystem access except where `tmp_path` is used intentionally (parser file I/O,
CLI file output tests). All diff content is inline string fixtures, not external files.

### 2. Integration tests

`test_report_builder.py` and `test_renderer.py` test the assembled pipeline using
`build_report_from_text()` with inline diffs. These verify that each module composes
correctly without mocking individual components.

### 3. CLI tests

`test_cli.py` calls `_execute(args)` directly (bypassing argparse) for most cases,
and patches `sys.argv` via `monkeypatch` for end-to-end tests through `main()`.
Both `capsys` and `tmp_path` are used extensively to verify stdout/stderr content
and file output.

### 4. Smoke test

`test_smoke.py` verifies that the package imports without error and that the
`reviewpilot` console script entry point is callable.

### Why MockAIClient in tests?

`MockAIClient` produces deterministic output: the same `AnalysisContext` always
produces the same `AIInsights`. This makes AI-touching tests reliable and reproducible.
A real API client would introduce network dependency, response variability, API key
management, and token cost into every test run — all unacceptable properties for
a unit test suite.

The mock is grounded: it only references file paths that exist in the context. Tests
can assert on specific strings in the AI sections (e.g., `assert "src/auth.py" in
regression_hypotheses[0]`) without fragility.

---

## Issues Caught During Development

### 1. pytest not installed globally

**Stage:** Iteration 2 (scaffold).
**Symptom:** `pytest` command not found.
**Resolution:** Created a `.venv` and installed with `pip install -e ".[dev]"`.
**Takeaway:** Always verify the test environment works before building on it.

### 2. Parser test fixture used a bare empty line

**Stage:** Iteration 4 (diff parser).
**Symptom:** `test_context_lines_have_correct_type` failed — expected 3 context
lines, got 2.
**Analysis:** Spent time verifying whether this was a parser bug or a test bug
before changing anything. Conclusion: the parser was correct. In unified diff
format, a blank context line must be `" "` (space + newline), not `""` (empty
string). The fixture had a bare empty line.
**Resolution:** Fixed the fixture. The parser was not modified.
**Takeaway:** Test failures caused by incorrect test fixtures are just as important
to catch as production bugs. AI-generated tests should be read and verified, not
just run.

### 3. Long PowerShell commands exceeded usable length

**Stage:** Iteration 10 (CLI).
**Symptom:** Ad-hoc PowerShell verification commands became unwieldy or produced
truncated output when written as long one-liners.
**Resolution:** Used `pytest` as the primary verification path. Pytest is structured,
repeatable, and produces clear pass/fail output regardless of command complexity.

### 4. `__main__.py` left untracked after CLI commit

**Stage:** Iteration 10 (CLI).
**Symptom:** After committing the CLI, `git status` showed `reviewpilot/__main__.py`
as untracked. The `python -m reviewpilot` entry point was missing from the commit.
**Resolution:** Staged the file and amended the commit.
**Takeaway:** Always run `git status` after committing. Files that are not imported
by other modules — like `__main__.py` — are easy to miss during staging.

---

## What I Chose Not To Test

Some behaviors were intentionally left without direct test coverage:

- **Real LLM output quality.** The `MockAIClient` tests the pipeline but not the
  quality of actual LLM suggestions. A golden-output evaluation set would be needed
  to test real AI responses.

- **Very large diffs.** No performance or memory tests. The tool is designed for
  typical PR sizes; multi-MB diffs were not a design target.

- **Malformed diff edge cases beyond empty input.** The parser handles standard
  `git diff` output. Corrupted or truncated diffs are not explicitly tested beyond
  the "no parseable files" error.

- **Concurrent use.** The tool is a CLI with no shared state — concurrency is not
  a concern for this scope.

- **Windows vs macOS path separator differences.** The classifier normalizes
  backslashes to forward slashes, but cross-platform path edge cases are not
  exhaustively tested.

---

## Current Limitations

1. **Input:** Local `.diff` files only. No GitHub/GitLab integration. No piped input.
2. **AI backend:** `MockAIClient` only. No real LLM output in the current MVP.
3. **Risk scoring:** Heuristic and keyword-based. No semantic analysis, AST parsing,
   or control-flow understanding.
4. **Repository context:** The tool operates on the diff in isolation. No repository
   history, no test coverage metrics, no dependency graph analysis.
5. **Runtime behavior:** The tool cannot verify whether a change breaks tests or
   alters runtime behavior.
6. **Language coverage:** File classification covers common extensions but is not
   exhaustive for all programming ecosystems.

---

## Future Improvements

These items are explicitly out of MVP scope but designed for:

- **Real Anthropic API client.** The `AIClient` Protocol is ready. Implement
  `AnthropicAIClient.generate_insights()` and pass it to the CLI via `--ai-client`.
  No other module changes required.

- **GitHub PR integration.** Fetch diffs via the GitHub API and post the generated
  report as a PR comment. The report format (Markdown) is already suitable.

- **Configurable risk rules.** Load signal weights and keyword sets from a
  `reviewpilot.toml` file rather than hardcoded constants. Different teams have
  different risk tolerances.

- **Repository-aware context.** Enrich `AnalysisContext` with recent commit history
  for touched files, test coverage data, and cross-PR patterns.

- **Golden output evaluation.** Maintain a set of reference diffs with expected
  report sections for regression-testing the AI layer across model versions.

- **CI integration.** Run ReviewPilot as a GitHub Actions step. Post the report
  as a PR comment automatically.

- **Richer output formats.** HTML report with collapsible sections, SARIF format
  for integration with GitHub Code Scanning.

---

## Final Reflection

The most important engineering decision in this project was the AI boundary: the
choice to build a deterministic analysis layer that stands on its own before asking
the AI for anything. This was not the simplest path — it would have been faster to
write "send the diff to Claude and return the response." But that approach would
have produced:

- an untestable core (LLM output is non-deterministic)
- an opaque output (no way to explain why a file was flagged)
- a fragile tool (any prompt change alters all outputs)

The `AnalysisContext` boundary solves all three: the deterministic layer is fully
tested, the risk signals are explainable, and the AI input is stable enough to
version and evaluate.

The other persistent theme was verification. Every AI-generated code change was
reviewed before committing. The parser fixture bug was found because the test output
was read carefully rather than assumed correct. The `__main__.py` omission was caught
because `git status` was checked after committing. AI-assisted development moves
faster when you maintain the habit of checking the output — not slower.
