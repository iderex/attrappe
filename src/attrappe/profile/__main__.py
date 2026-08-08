"""Validate a profile directory from the command line.

    python -m attrappe.profile <directory>

Non-zero when the profile is refused, with every problem printed to standard
error. There is no console entry point for this: naming one is #55's, and the
operator-facing subcommand is #27's.
"""

from attrappe.profile.loader import main

if __name__ == "__main__":
    raise SystemExit(main())
