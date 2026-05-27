# ReviewPilot — Claude Code Instructions

This file provides context for Claude Code sessions working on this project.

## What this project is

ReviewPilot is a Python CLI tool that analyzes a local git diff file and generates
a structured Markdown PR review report. It is a small, demo-able project built
as a recruitment assignment to showcase AI-assisted engineering judgment.

## Core architecture principle

**Hard separation between deterministic and AI-assisted layers.**

| Layer | Modules | Rule |
|---|---|---|
| Deterministic | `parser`, `classifier`, `risk_scorer` | No LLM calls. Fully unit-testable. |
| AI | `ai_client` | Never receives raw diff text. Receives `AnalysisContext`. |
| Assembly | `report_builder`, `renderer` | Wires layers together. No business logic. |
| CLI | `cli` | argparse only. No extra dependencies. |

## Conventions

- Python 3.11+ only. Use modern typing (`X | Y`, `match`, etc.).
- All data models live in `models.py` (typed dataclasses).
- All business logic must have corresponding pytest tests in `tests/`.
- Tests always use `MockAIClient` — no real API calls anywhere in the test suite.
- AI-generated sections in the report output are explicitly labeled as such.
- Update `dev_log.md` after each significant implementation step.

## Do NOT

- Add real Anthropic API integration (the interface is ready; keep it wired to mock for now).
- Add GitHub / GitLab API integration (out of MVP scope).
- Add dependencies beyond `pytest` and `pytest-cov` in the dev extras.
- Implement a module without also implementing its tests.

## Running the project

```bash
pip install -e ".[dev]"   # install with dev dependencies
pytest                     # run all tests
pytest -v                  # verbose output
pytest --cov=reviewpilot  # with coverage report
python -m reviewpilot examples/simple_bugfix.diff
python -m reviewpilot examples/simple_bugfix.diff --output reports/my_report.md
```

## Key files (read these first when picking up context)

- `reviewpilot/models.py` — all data models; understand these before touching anything else
- `reviewpilot/ai_client.py` — `AIClient` protocol and `MockAIClient`
- `reviewpilot/report_builder.py` — main pipeline orchestration
- `dev_log.md` — history of all decisions, prompt iterations, and reflections

## Commit style

Small, focused commits. Each commit leaves `pytest` passing.
Format: `<type>: <short description>` (e.g., `feat: diff parser`, `test: risk scorer tests`).
