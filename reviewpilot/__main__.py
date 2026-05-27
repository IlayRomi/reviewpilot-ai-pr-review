"""
Package entry point for `python -m reviewpilot`.

Delegates directly to cli.main() so the behaviour is identical whether
the user runs `reviewpilot <args>` (console script) or
`python -m reviewpilot <args>`.
"""

from reviewpilot.cli import main

if __name__ == "__main__":
    main()
