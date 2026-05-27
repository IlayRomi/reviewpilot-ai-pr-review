"""
Smoke tests — Commit #1 (scaffold).

Verify that the package and all submodules import cleanly.
These tests contain no business logic; they exist to catch structural
problems (missing files, syntax errors, bad imports) early.
"""


def test_package_importable() -> None:
    """Package root imports and exposes a version string."""
    import reviewpilot

    assert isinstance(reviewpilot.__version__, str), "Missing __version__"
    assert len(reviewpilot.__version__) > 0, "__version__ must not be empty"


def test_all_modules_importable() -> None:
    """Every submodule imports without raising an exception."""
    from reviewpilot import models          # noqa: F401
    from reviewpilot import parser          # noqa: F401
    from reviewpilot import classifier      # noqa: F401
    from reviewpilot import risk_scorer     # noqa: F401
    from reviewpilot import ai_client       # noqa: F401
    from reviewpilot import report_builder  # noqa: F401
    from reviewpilot import renderer        # noqa: F401
    from reviewpilot import cli             # noqa: F401


def test_cli_main_callable() -> None:
    """cli.main is defined and callable (scaffold placeholder)."""
    from reviewpilot.cli import main
    import inspect

    assert callable(main), "cli.main must be callable"
    sig = inspect.signature(main)
    assert len(sig.parameters) == 0, "cli.main() takes no arguments"
