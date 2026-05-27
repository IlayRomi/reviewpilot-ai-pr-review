"""
File classifier module.

Responsibility: Given a file path (string), determine the FileRole of that file
within the project. Role classification drives risk scoring weights downstream.

Classification is purely deterministic — pattern matching on file paths and
extensions. No AI involvement.

FileRole categories (defined in models.py):
    SOURCE      — application source code (e.g., *.py, *.js, *.go)
    TEST        — test files (e.g., test_*.py, *.test.ts, *_spec.rb)
    CONFIG      — configuration files (e.g., *.yaml, *.toml, *.env, Dockerfile)
    MIGRATION   — database migration files (e.g., migrations/*.sql, *.migration.py)
    DOCS        — documentation (e.g., *.md, *.rst, docs/)
    INFRA       — infrastructure / CI (e.g., .github/workflows/, terraform/)
    UNKNOWN     — does not match any known pattern

Public interface (to be implemented in Commit #4):
    classify_file(filename: str) -> FileRole
        Return the FileRole for a given file path string.
"""

# Implementation will be added in Commit #4.
