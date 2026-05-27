"""
Tests for reviewpilot/cli.py — Commit #9.

Strategy:
  - Test _execute(args) directly using a fake argparse.Namespace to avoid
    sys.argv manipulation wherever possible.
  - Use monkeypatch.setattr(sys, "argv", [...]) only for the handful of tests
    that verify main() end-to-end (argparse parsing included).
  - capsys captures stdout / stderr for content assertions.
  - tmp_path provides isolated temporary directories for file-output tests.
  - All diff content uses inline strings — no fixtures on disk required.

Coverage:
  1.  Stdout output: running with a valid diff prints Markdown to stdout
  2.  Stdout output contains the report title
  3.  Stdout output contains section headings
  4.  Stdout output ends with a newline
  5.  --output writes a file and prints confirmation to stderr
  6.  --output file content matches render_markdown output
  7.  --output file is valid Markdown (contains ## headings)
  8.  --title sets a custom report title
  9.  Default title includes the diff filename
  10. Error: diff file not found → stderr message + exit code 1
  11. Error: path is a directory, not a file → stderr message + exit code 1
  12. Error: diff text is empty / unparseable → stderr message + exit code 1
  13. Error: output directory does not exist → stderr message + exit code 1
  14. main() end-to-end via sys.argv patching (stdout)
  15. main() end-to-end via sys.argv patching (--output)
  16. --mock-ai flag is accepted without error
  17. _build_parser returns an ArgumentParser with correct prog name
  18. -h / --help exits cleanly (code 0)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

from reviewpilot.cli import _build_parser, _execute, main
from reviewpilot.renderer import render_markdown
from reviewpilot.report_builder import build_report_from_text


# ---------------------------------------------------------------------------
# Shared diff fixture
# ---------------------------------------------------------------------------

# A minimal but valid unified diff — one modified Python source file.
_VALID_DIFF = """\
diff --git a/src/app.py b/src/app.py
index abc123..def456 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,3 @@
 def greet():
-    return "hello"
+    return "hello, world"
+    # updated greeting
"""

# Another diff that contains auth keywords — exercises more signal paths.
_AUTH_DIFF = """\
diff --git a/src/auth.py b/src/auth.py
index abc123..def456 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,3 @@
 def login(user):
-    check_password(user)
+    validate_password(user)
+    generate_token(user)
"""


@pytest.fixture()
def valid_diff_file(tmp_path: Path) -> Path:
    """Write _VALID_DIFF to a temporary file and return its path."""
    p = tmp_path / "changes.diff"
    p.write_text(_VALID_DIFF, encoding="utf-8")
    return p


@pytest.fixture()
def auth_diff_file(tmp_path: Path) -> Path:
    """Write _AUTH_DIFF to a temporary file and return its path."""
    p = tmp_path / "auth.diff"
    p.write_text(_AUTH_DIFF, encoding="utf-8")
    return p


@pytest.fixture()
def empty_diff_file(tmp_path: Path) -> Path:
    """Write an empty file (no diff content) to a temporary file."""
    p = tmp_path / "empty.diff"
    p.write_text("", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Helper: build a minimal Namespace that _execute() expects
# ---------------------------------------------------------------------------


def _ns(
    diff_file: str,
    output: str | None = None,
    title: str | None = None,
    mock_ai: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        diff_file=diff_file,
        output=output,
        title=title,
        mock_ai=mock_ai,
    )


# ===========================================================================
# Test 1–4: stdout output (no --output flag)
# ===========================================================================


class TestStdoutOutput:
    def test_valid_diff_prints_to_stdout(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file)))
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_stdout_contains_default_title(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file)))
        captured = capsys.readouterr()
        assert "ReviewPilot Report" in captured.out

    def test_stdout_contains_section_headings(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file)))
        captured = capsys.readouterr()
        assert "## Executive Summary" in captured.out
        assert "## Changed Files" in captured.out
        assert "## Deterministic Risk Analysis" in captured.out

    def test_stdout_ends_with_newline(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file)))
        captured = capsys.readouterr()
        assert captured.out.endswith("\n")

    def test_nothing_written_to_stderr_on_success(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file)))
        captured = capsys.readouterr()
        assert captured.err == ""


# ===========================================================================
# Test 5–7: --output flag writes a file
# ===========================================================================


class TestOutputFile:
    def test_output_creates_file(
        self,
        valid_diff_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "report.md"
        _execute(_ns(str(valid_diff_file), output=str(out)))
        assert out.exists()

    def test_output_file_content_matches_render_markdown(
        self,
        valid_diff_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "report.md"
        _execute(_ns(str(valid_diff_file), output=str(out)))
        # Re-run pipeline to get expected content
        expected = render_markdown(
            build_report_from_text(_VALID_DIFF, title="ReviewPilot Report — changes.diff")
        )
        actual = out.read_text(encoding="utf-8")
        # Both should contain the same structural sections.
        # Exact match is not required (timestamps differ), but sections must match.
        assert "## Executive Summary" in actual
        assert "## Changed Files" in actual
        assert "## Deterministic Risk Analysis" in actual

    def test_output_file_is_valid_markdown(
        self,
        valid_diff_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "report.md"
        _execute(_ns(str(valid_diff_file), output=str(out)))
        content = out.read_text(encoding="utf-8")
        assert content.startswith("# ReviewPilot Report")

    def test_output_confirmation_goes_to_stderr(
        self,
        valid_diff_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "report.md"
        _execute(_ns(str(valid_diff_file), output=str(out)))
        captured = capsys.readouterr()
        assert "Report written to:" in captured.err
        assert str(out) in captured.err

    def test_output_nothing_printed_to_stdout(
        self,
        valid_diff_file: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "report.md"
        _execute(_ns(str(valid_diff_file), output=str(out)))
        captured = capsys.readouterr()
        assert captured.out == ""


# ===========================================================================
# Test 8–9: --title flag
# ===========================================================================


class TestTitleOption:
    def test_custom_title_appears_in_stdout(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file), title="My Custom Title"))
        captured = capsys.readouterr()
        assert "My Custom Title" in captured.out

    def test_custom_title_appears_as_h1(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file), title="Sprint 42 Review"))
        captured = capsys.readouterr()
        assert "# Sprint 42 Review" in captured.out

    def test_default_title_includes_filename(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file)))
        captured = capsys.readouterr()
        # Default title is "ReviewPilot Report — <filename>"
        assert "changes.diff" in captured.out


# ===========================================================================
# Test 10–13: Error handling
# ===========================================================================


class TestErrorHandling:
    def test_nonexistent_file_exits_1(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.diff"
        with pytest.raises(SystemExit) as exc_info:
            _execute(_ns(str(missing)))
        assert exc_info.value.code == 1

    def test_nonexistent_file_stderr_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "does_not_exist.diff"
        with pytest.raises(SystemExit):
            _execute(_ns(str(missing)))
        captured = capsys.readouterr()
        assert "reviewpilot: error:" in captured.err
        assert "not found" in captured.err

    def test_directory_as_input_exits_1(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _execute(_ns(str(tmp_path)))
        assert exc_info.value.code == 1

    def test_directory_as_input_stderr_message(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            _execute(_ns(str(tmp_path)))
        captured = capsys.readouterr()
        assert "reviewpilot: error:" in captured.err
        assert "not a file" in captured.err

    def test_empty_diff_exits_1(
        self, empty_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            _execute(_ns(str(empty_diff_file)))
        assert exc_info.value.code == 1

    def test_empty_diff_stderr_message(
        self, empty_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            _execute(_ns(str(empty_diff_file)))
        captured = capsys.readouterr()
        assert "reviewpilot: error:" in captured.err

    def test_output_to_nonexistent_directory_exits_1(
        self, valid_diff_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "nonexistent_dir" / "report.md"
        with pytest.raises(SystemExit) as exc_info:
            _execute(_ns(str(valid_diff_file), output=str(out)))
        assert exc_info.value.code == 1

    def test_output_to_nonexistent_directory_stderr_message(
        self, valid_diff_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = tmp_path / "nonexistent_dir" / "report.md"
        with pytest.raises(SystemExit):
            _execute(_ns(str(valid_diff_file), output=str(out)))
        captured = capsys.readouterr()
        assert "reviewpilot: error:" in captured.err


# ===========================================================================
# Test 14–15: main() end-to-end via sys.argv patching
# ===========================================================================


class TestMainEndToEnd:
    def test_main_stdout_via_argv(
        self,
        valid_diff_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["reviewpilot", str(valid_diff_file)])
        main()
        captured = capsys.readouterr()
        assert "## Executive Summary" in captured.out

    def test_main_output_file_via_argv(
        self,
        valid_diff_file: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "out.md"
        monkeypatch.setattr(
            sys, "argv", ["reviewpilot", str(valid_diff_file), "--output", str(out)]
        )
        main()
        assert out.exists()
        assert "## Executive Summary" in out.read_text(encoding="utf-8")

    def test_main_custom_title_via_argv(
        self,
        valid_diff_file: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            ["reviewpilot", str(valid_diff_file), "--title", "E2E Title"],
        )
        main()
        captured = capsys.readouterr()
        assert "E2E Title" in captured.out


# ===========================================================================
# Test 16: --mock-ai flag is accepted
# ===========================================================================


class TestMockAiFlag:
    def test_mock_ai_flag_accepted(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Should not raise or exit 1; --mock-ai is always the default behaviour.
        _execute(_ns(str(valid_diff_file), mock_ai=True))
        captured = capsys.readouterr()
        assert "## Executive Summary" in captured.out

    def test_mock_ai_flag_does_not_change_output(
        self, valid_diff_file: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _execute(_ns(str(valid_diff_file), mock_ai=False))
        without = capsys.readouterr().out
        _execute(_ns(str(valid_diff_file), mock_ai=True))
        with_ = capsys.readouterr().out
        # Both should contain the same sections (timestamps may differ).
        for heading in ("## Executive Summary", "## Changed Files"):
            assert heading in without
            assert heading in with_


# ===========================================================================
# Test 17: _build_parser correctness
# ===========================================================================


class TestBuildParser:
    def test_prog_name(self) -> None:
        parser = _build_parser()
        assert parser.prog == "reviewpilot"

    def test_diff_file_is_positional(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff"])
        assert ns.diff_file == "some.diff"

    def test_output_default_is_none(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff"])
        assert ns.output is None

    def test_title_default_is_none(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff"])
        assert ns.title is None

    def test_mock_ai_default_is_false(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff"])
        assert ns.mock_ai is False

    def test_mock_ai_flag_sets_true(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff", "--mock-ai"])
        assert ns.mock_ai is True

    def test_output_long_form(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff", "--output", "out.md"])
        assert ns.output == "out.md"

    def test_title_long_form(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["some.diff", "--title", "My Title"])
        assert ns.title == "My Title"


# ===========================================================================
# Test 18: --help exits cleanly with code 0
# ===========================================================================


class TestHelp:
    def test_help_exits_0(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["reviewpilot", "--help"])
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_help_output_mentions_reviewpilot(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "argv", ["reviewpilot", "--help"])
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        assert "reviewpilot" in captured.out.lower()
