"""
Tests for reviewpilot/classifier.py — Commit #4.

Coverage:
  1.  None and empty path                         → UNKNOWN
  2.  Python source under src/                    → SOURCE
  3a. Test files by directory (tests/, test/)     → TEST
  3b. Test files by filename convention           → TEST
  3c. Test files by JS/TS suffix conventions      → TEST
  4.  Config files (names, dirs, extensions)      → CONFIG
  5.  Migration files                             → MIGRATION
  6.  Docs files (dirs, extensions)               → DOCS
  7.  Infra files (Dockerfile, CI, Terraform, k8s)→ INFRA
  8.  Truly unknown files                         → UNKNOWN
  9.  Windows-style backslash paths               → correctly classified
  10. Precedence: test beats source, infra beats config
"""

import pytest

from reviewpilot.models import FileRole
from reviewpilot.classifier import classify_file


# ---------------------------------------------------------------------------
# 1. None and empty / whitespace paths
# ---------------------------------------------------------------------------


class TestNoneAndEmpty:
    def test_none_returns_unknown(self) -> None:
        assert classify_file(None) is FileRole.UNKNOWN

    def test_empty_string_returns_unknown(self) -> None:
        assert classify_file("") is FileRole.UNKNOWN

    def test_whitespace_only_returns_unknown(self) -> None:
        assert classify_file("   ") is FileRole.UNKNOWN

    def test_tab_only_returns_unknown(self) -> None:
        assert classify_file("\t") is FileRole.UNKNOWN


# ---------------------------------------------------------------------------
# 2. SOURCE files
# ---------------------------------------------------------------------------


class TestSourceFiles:
    def test_python_under_src(self) -> None:
        assert classify_file("src/app.py") is FileRole.SOURCE

    def test_python_under_lib(self) -> None:
        assert classify_file("lib/utils.py") is FileRole.SOURCE

    def test_python_under_app(self) -> None:
        assert classify_file("app/models.py") is FileRole.SOURCE

    def test_python_at_root_by_extension(self) -> None:
        assert classify_file("main.py") is FileRole.SOURCE

    def test_javascript_by_extension(self) -> None:
        assert classify_file("index.js") is FileRole.SOURCE

    def test_typescript_by_extension(self) -> None:
        assert classify_file("auth.ts") is FileRole.SOURCE

    def test_go_by_extension(self) -> None:
        assert classify_file("cmd/server.go") is FileRole.SOURCE

    def test_rust_by_extension(self) -> None:
        assert classify_file("src/main.rs") is FileRole.SOURCE

    def test_java_by_extension(self) -> None:
        assert classify_file("src/Main.java") is FileRole.SOURCE

    def test_nested_under_src(self) -> None:
        assert classify_file("src/api/handlers/auth.py") is FileRole.SOURCE


# ---------------------------------------------------------------------------
# 3a. TEST files — directory-based detection
# ---------------------------------------------------------------------------


class TestFilesByDirectory:
    def test_under_tests_dir(self) -> None:
        assert classify_file("tests/test_auth.py") is FileRole.TEST

    def test_under_test_singular_dir(self) -> None:
        assert classify_file("test/auth_test.py") is FileRole.TEST

    def test_any_file_under_tests(self) -> None:
        """Non-test-named file under tests/ is still TEST."""
        assert classify_file("tests/fixtures/sample.py") is FileRole.TEST

    def test_nested_under_tests(self) -> None:
        assert classify_file("src/api/tests/test_handlers.py") is FileRole.TEST

    def test_under_jest_tests_dir(self) -> None:
        assert classify_file("__tests__/auth.js") is FileRole.TEST


# ---------------------------------------------------------------------------
# 3b. TEST files — filename convention
# ---------------------------------------------------------------------------


class TestFilesByNamingConvention:
    def test_test_underscore_prefix(self) -> None:
        assert classify_file("test_auth.py") is FileRole.TEST

    def test_test_prefix_nested(self) -> None:
        assert classify_file("src/test_models.py") is FileRole.TEST

    def test_underscore_test_suffix_py(self) -> None:
        assert classify_file("auth_test.py") is FileRole.TEST

    def test_underscore_test_suffix_ts(self) -> None:
        assert classify_file("auth_test.ts") is FileRole.TEST


# ---------------------------------------------------------------------------
# 3c. TEST files — JS/TS suffix conventions
# ---------------------------------------------------------------------------


class TestFilesByJsTsSuffix:
    def test_dot_test_js(self) -> None:
        assert classify_file("auth.test.js") is FileRole.TEST

    def test_dot_spec_js(self) -> None:
        assert classify_file("auth.spec.js") is FileRole.TEST

    def test_dot_test_ts(self) -> None:
        assert classify_file("components/Button.test.ts") is FileRole.TEST

    def test_dot_spec_ts(self) -> None:
        assert classify_file("components/Button.spec.ts") is FileRole.TEST

    def test_dot_test_tsx(self) -> None:
        assert classify_file("components/Button.test.tsx") is FileRole.TEST

    def test_dot_spec_jsx(self) -> None:
        assert classify_file("components/Button.spec.jsx") is FileRole.TEST


# ---------------------------------------------------------------------------
# 4. CONFIG files
# ---------------------------------------------------------------------------


class TestConfigFiles:
    def test_pyproject_toml(self) -> None:
        assert classify_file("pyproject.toml") is FileRole.CONFIG

    def test_package_json(self) -> None:
        assert classify_file("package.json") is FileRole.CONFIG

    def test_package_lock_json(self) -> None:
        assert classify_file("package-lock.json") is FileRole.CONFIG

    def test_requirements_txt(self) -> None:
        assert classify_file("requirements.txt") is FileRole.CONFIG

    def test_requirements_dev_txt(self) -> None:
        assert classify_file("requirements-dev.txt") is FileRole.CONFIG

    def test_setup_py(self) -> None:
        assert classify_file("setup.py") is FileRole.CONFIG

    def test_dot_env(self) -> None:
        assert classify_file(".env") is FileRole.CONFIG

    def test_dot_env_example(self) -> None:
        assert classify_file(".env.example") is FileRole.CONFIG

    def test_yaml_extension(self) -> None:
        assert classify_file("app.yaml") is FileRole.CONFIG

    def test_yml_extension(self) -> None:
        assert classify_file("settings.yml") is FileRole.CONFIG

    def test_toml_extension(self) -> None:
        assert classify_file("rust.toml") is FileRole.CONFIG

    def test_ini_extension(self) -> None:
        assert classify_file("tox.ini") is FileRole.CONFIG

    def test_under_config_dir(self) -> None:
        assert classify_file("config/settings.py") is FileRole.CONFIG

    def test_nested_under_config_dir(self) -> None:
        assert classify_file("src/config/database.py") is FileRole.CONFIG

    def test_tsconfig_json(self) -> None:
        assert classify_file("tsconfig.json") is FileRole.CONFIG

    def test_jest_config_json(self) -> None:
        """JSON files with 'config' in the name → CONFIG."""
        assert classify_file("jest.config.json") is FileRole.CONFIG


# ---------------------------------------------------------------------------
# 5. MIGRATION files
# ---------------------------------------------------------------------------


class TestMigrationFiles:
    def test_under_migrations_dir(self) -> None:
        assert classify_file("migrations/001_create_users.sql") is FileRole.MIGRATION

    def test_under_migration_singular_dir(self) -> None:
        assert classify_file("migration/add_index.py") is FileRole.MIGRATION

    def test_nested_migrations_path(self) -> None:
        assert classify_file("db/migrations/002_add_column.py") is FileRole.MIGRATION

    def test_migration_in_filename(self) -> None:
        assert classify_file("20240101_migration_add_users.py") is FileRole.MIGRATION

    def test_alembic_style_path(self) -> None:
        """Alembic 'versions/' paths that include 'migration' in the file name."""
        assert classify_file("alembic/versions/abc123_migration.py") is FileRole.MIGRATION


# ---------------------------------------------------------------------------
# 6. DOCS files
# ---------------------------------------------------------------------------


class TestDocsFiles:
    def test_readme_md(self) -> None:
        assert classify_file("README.md") is FileRole.DOCS

    def test_markdown_by_extension(self) -> None:
        assert classify_file("CONTRIBUTING.md") is FileRole.DOCS

    def test_rst_extension(self) -> None:
        assert classify_file("docs/api.rst") is FileRole.DOCS

    def test_txt_extension(self) -> None:
        assert classify_file("CHANGELOG.txt") is FileRole.DOCS

    def test_under_docs_dir(self) -> None:
        assert classify_file("docs/getting_started.md") is FileRole.DOCS

    def test_under_doc_singular_dir(self) -> None:
        assert classify_file("doc/architecture.md") is FileRole.DOCS

    def test_nested_under_docs(self) -> None:
        assert classify_file("docs/api/endpoints.md") is FileRole.DOCS


# ---------------------------------------------------------------------------
# 7. INFRA files
# ---------------------------------------------------------------------------


class TestInfraFiles:
    def test_dockerfile(self) -> None:
        assert classify_file("Dockerfile") is FileRole.INFRA

    def test_dockerfile_variant(self) -> None:
        assert classify_file("Dockerfile.prod") is FileRole.INFRA

    def test_docker_compose_yml(self) -> None:
        assert classify_file("docker-compose.yml") is FileRole.INFRA

    def test_docker_compose_yaml(self) -> None:
        assert classify_file("docker-compose.yaml") is FileRole.INFRA

    def test_github_workflow(self) -> None:
        assert classify_file(".github/workflows/ci.yml") is FileRole.INFRA

    def test_github_workflow_nested(self) -> None:
        assert classify_file(".github/workflows/deploy.yaml") is FileRole.INFRA

    def test_terraform_tf_extension(self) -> None:
        assert classify_file("main.tf") is FileRole.INFRA

    def test_terraform_tfvars(self) -> None:
        assert classify_file("terraform.tfvars") is FileRole.INFRA

    def test_under_infra_dir(self) -> None:
        assert classify_file("infra/ecs_task.json") is FileRole.INFRA

    def test_under_k8s_dir(self) -> None:
        assert classify_file("k8s/deployment.yaml") is FileRole.INFRA

    def test_under_kubernetes_dir(self) -> None:
        assert classify_file("kubernetes/service.yaml") is FileRole.INFRA


# ---------------------------------------------------------------------------
# 8. UNKNOWN files
# ---------------------------------------------------------------------------


class TestUnknownFiles:
    def test_csv_file(self) -> None:
        assert classify_file("data/users.csv") is FileRole.UNKNOWN

    def test_unknown_extension(self) -> None:
        assert classify_file("file.xyz123") is FileRole.UNKNOWN

    def test_binary_like_extension(self) -> None:
        assert classify_file("assets/logo.png") is FileRole.UNKNOWN

    def test_sql_outside_migration(self) -> None:
        """SQL file not in a migration path → UNKNOWN (not a source extension)."""
        assert classify_file("reports/monthly_sales.sql") is FileRole.UNKNOWN

    def test_lock_file_outside_known(self) -> None:
        """A .lock file that isn't yarn.lock → UNKNOWN."""
        assert classify_file("Gemfile.lock") is FileRole.UNKNOWN


# ---------------------------------------------------------------------------
# 9. Windows-style backslash paths
# ---------------------------------------------------------------------------


class TestWindowsPaths:
    def test_windows_test_path(self) -> None:
        assert classify_file("tests\\test_auth.py") is FileRole.TEST

    def test_windows_source_path(self) -> None:
        assert classify_file("src\\app.py") is FileRole.SOURCE

    def test_windows_migration_path(self) -> None:
        assert classify_file("migrations\\001_create_users.sql") is FileRole.MIGRATION

    def test_windows_config_path(self) -> None:
        assert classify_file("config\\settings.yml") is FileRole.CONFIG

    def test_windows_infra_path(self) -> None:
        assert classify_file(".github\\workflows\\ci.yml") is FileRole.INFRA

    def test_windows_docs_path(self) -> None:
        assert classify_file("docs\\api.md") is FileRole.DOCS

    def test_windows_deep_nested(self) -> None:
        assert classify_file("src\\api\\handlers\\auth.py") is FileRole.SOURCE


# ---------------------------------------------------------------------------
# 10. Precedence rules
# ---------------------------------------------------------------------------


class TestPrecedence:
    """TEST and INFRA must win over SOURCE and CONFIG respectively."""

    # TEST beats SOURCE
    def test_test_prefix_under_src(self) -> None:
        """test_*.py under src/ → TEST, not SOURCE."""
        assert classify_file("src/test_auth.py") is FileRole.TEST

    def test_tests_dir_under_src(self) -> None:
        """src/tests/ → TEST, not SOURCE."""
        assert classify_file("src/tests/test_models.py") is FileRole.TEST

    def test_test_suffix_under_app(self) -> None:
        """app/auth_test.py → TEST, not SOURCE."""
        assert classify_file("app/auth_test.py") is FileRole.TEST

    def test_ts_spec_file_under_src(self) -> None:
        """src/auth.spec.ts → TEST, not SOURCE."""
        assert classify_file("src/auth.spec.ts") is FileRole.TEST

    # INFRA beats CONFIG (.yml / .yaml extension conflict)
    def test_docker_compose_is_infra_not_config(self) -> None:
        """docker-compose.yml has .yml extension but must be INFRA."""
        assert classify_file("docker-compose.yml") is FileRole.INFRA

    def test_github_workflow_is_infra_not_config(self) -> None:
        """.github/workflows/ci.yml has .yml extension but must be INFRA."""
        assert classify_file(".github/workflows/ci.yml") is FileRole.INFRA

    def test_k8s_yaml_is_infra_not_config(self) -> None:
        """k8s/deployment.yaml has .yaml extension but must be INFRA."""
        assert classify_file("k8s/deployment.yaml") is FileRole.INFRA

    def test_terraform_file_is_infra_not_unknown(self) -> None:
        """main.tf → INFRA, not UNKNOWN."""
        assert classify_file("main.tf") is FileRole.INFRA

    # CONFIG beats DOCS (.txt extension conflict)
    def test_requirements_txt_is_config_not_docs(self) -> None:
        """requirements.txt has .txt extension but must be CONFIG."""
        assert classify_file("requirements.txt") is FileRole.CONFIG
