"""
File classifier module.

Responsibility: Given a file path string, return the FileRole that best
describes the file's function in the project.

Classification is purely deterministic — path normalization + pattern matching.
No AI involvement.

Priority order (highest wins):
    TEST > MIGRATION > INFRA > CONFIG > DOCS > SOURCE > UNKNOWN

Keeping INFRA before CONFIG ensures that docker-compose.yml or GitHub Actions
YAML files are not mis-classified as CONFIG due to their .yml extension.
Keeping TEST first ensures that test files under src/ or with .py extensions
are always classified as TEST, never as SOURCE.

Public interface:
    classify_file(path: str | None) -> FileRole
        Classify a single file path. Returns FileRole.UNKNOWN for None/empty.
"""

from __future__ import annotations

import os

from reviewpilot.models import FileRole


# ---------------------------------------------------------------------------
# Constants  (all lowercase — matched against normalized paths / filenames)
# ---------------------------------------------------------------------------

# Exact filename matches → CONFIG
_CONFIG_FILENAMES: frozenset[str] = frozenset(
    {
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
        "setup.py",
        "setup.cfg",
        ".env",
        ".env.example",
        ".env.local",
        "tsconfig.json",
        ".eslintrc",
        ".eslintrc.json",
        ".prettierrc",
        ".prettierrc.json",
        ".babelrc",
        ".babelrc.json",
        "jest.config.js",
        "jest.config.ts",
        "webpack.config.js",
        "vite.config.js",
        "vite.config.ts",
        "makefile",
        "tox.ini",
        "pytest.ini",
        ".flake8",
        "mypy.ini",
        ".mypy.ini",
    }
)

# Exact filename matches → INFRA (checked before CONFIG to win on .yml files)
_INFRA_FILENAMES: frozenset[str] = frozenset(
    {
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "docker-compose.override.yml",
        "docker-compose.override.yaml",
        "vagrantfile",
    }
)

# Directory segments whose presence alone makes a path INFRA
_INFRA_DIRS: tuple[str, ...] = (
    "infra",
    "infrastructure",
    "k8s",
    "kubernetes",
    "terraform",
    "deploy",
)

# File extensions → CONFIG
_CONFIG_EXTENSIONS: frozenset[str] = frozenset(
    {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf"}
)

# File extensions → DOCS
_DOCS_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})

# File extensions → SOURCE
_SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".java",
        ".go",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".rs",
        ".rb",
        ".kt",
        ".swift",
        ".scala",
        ".cs",
        ".php",
        ".lua",
    }
)

# Directory segments whose presence alone makes a path SOURCE
_SOURCE_DIRS: tuple[str, ...] = ("src", "app", "lib")

# Filename suffixes → TEST (JS/TS conventions)
_TEST_SUFFIXES: tuple[str, ...] = (
    ".test.js",
    ".spec.js",
    ".test.ts",
    ".spec.ts",
    ".test.jsx",
    ".spec.jsx",
    ".test.tsx",
    ".spec.tsx",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_file(path: str | None) -> FileRole:
    """Classify a changed file path into a FileRole.

    Normalizes the path to lowercase with forward slashes before matching,
    so Windows-style paths (backslashes) are handled transparently.

    Priority order: TEST > MIGRATION > INFRA > CONFIG > DOCS > SOURCE > UNKNOWN

    Args:
        path: File path string (relative or absolute). None or empty → UNKNOWN.

    Returns:
        The most specific matching FileRole.
    """
    if not path or not path.strip():
        return FileRole.UNKNOWN

    # Normalize: strip whitespace, lowercase, unify separators
    normalized = path.strip().lower().replace("\\", "/")

    # Extract bare filename (last path component)
    filename = normalized.rsplit("/", 1)[-1]

    if _is_test(normalized, filename):
        return FileRole.TEST
    if _is_migration(normalized, filename):
        return FileRole.MIGRATION
    if _is_infra(normalized, filename):
        return FileRole.INFRA
    if _is_config(normalized, filename):
        return FileRole.CONFIG
    if _is_docs(normalized, filename):
        return FileRole.DOCS
    if _is_source(normalized, filename):
        return FileRole.SOURCE

    return FileRole.UNKNOWN


# ---------------------------------------------------------------------------
# Private classifiers
# ---------------------------------------------------------------------------


def _is_test(normalized: str, filename: str) -> bool:
    """Return True if the file is a test file."""
    # Directory-based: tests/, test/, __tests__/
    for dirname in ("tests", "test", "__tests__"):
        if _path_has_dir(normalized, dirname):
            return True
    # Filename conventions: test_foo.py, foo_test.py, foo_test.ts
    if filename.startswith("test_"):
        return True
    if filename.endswith("_test.py") or filename.endswith("_test.ts"):
        return True
    # JS/TS: foo.test.ts, foo.spec.js, etc.
    for suffix in _TEST_SUFFIXES:
        if filename.endswith(suffix):
            return True
    return False


def _is_migration(normalized: str, filename: str) -> bool:
    """Return True if the file is a database migration.

    Matches any path containing 'migration' (covers both 'migration' and
    'migrations' as substrings).
    """
    return "migration" in normalized


def _is_infra(normalized: str, filename: str) -> bool:
    """Return True if the file is infrastructure / CI / deployment code."""
    # Exact filename match (e.g. Dockerfile, docker-compose.yml)
    if filename in _INFRA_FILENAMES:
        return True
    # Dockerfile.prod, Dockerfile.dev, etc.
    if filename.startswith("dockerfile"):
        return True
    # GitHub Actions workflows
    if ".github/workflows/" in normalized:
        return True
    # Infrastructure directories
    for dirname in _INFRA_DIRS:
        if _path_has_dir(normalized, dirname):
            return True
    # Terraform files
    _, ext = os.path.splitext(filename)
    if ext in (".tf", ".tfvars"):
        return True
    return False


def _is_config(normalized: str, filename: str) -> bool:
    """Return True if the file is a project configuration file."""
    # Exact filename match
    if filename in _CONFIG_FILENAMES:
        return True
    # Under a config/ directory
    if _path_has_dir(normalized, "config"):
        return True
    # Common config extensions (.yaml, .yml, .toml, .ini, .cfg, .conf)
    _, ext = os.path.splitext(filename)
    if ext in _CONFIG_EXTENSIONS:
        return True
    # JSON files with config-like names: tsconfig.json, .eslintrc.json, etc.
    if ext == ".json" and ("config" in filename or filename.startswith(".")):
        return True
    return False


def _is_docs(normalized: str, filename: str) -> bool:
    """Return True if the file is documentation."""
    # Under docs/ or doc/ directory
    if _path_has_dir(normalized, "docs") or _path_has_dir(normalized, "doc"):
        return True
    # Doc extensions: .md, .rst, .txt
    _, ext = os.path.splitext(filename)
    if ext in _DOCS_EXTENSIONS:
        return True
    return False


def _is_source(normalized: str, filename: str) -> bool:
    """Return True if the file is application source code."""
    # Source directories
    for dirname in _SOURCE_DIRS:
        if _path_has_dir(normalized, dirname):
            return True
    # Source extensions
    _, ext = os.path.splitext(filename)
    if ext in _SOURCE_EXTENSIONS:
        return True
    return False


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _path_has_dir(normalized: str, dirname: str) -> bool:
    """Return True if a normalized path contains dirname as a path segment.

    Handles both leading-segment (dirname/...) and mid-path (.../ dirname/...)
    forms. Does not match partial directory names (e.g. 'test' does not match
    inside 'latest/').

    Args:
        normalized: Lowercase, forward-slash path string.
        dirname:    Lowercase directory name to search for (no slashes).
    """
    return f"/{dirname}/" in normalized or normalized.startswith(f"{dirname}/")
