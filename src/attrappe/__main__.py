"""Run the emulator from the command line.

    python -m attrappe run <profile>

`attrappe.cli` is where the surface is described and where the exit codes are
fixed. This file is the module entry point and nothing else. A console script,
so that the command is one word with no module path in front of it, is #55's:
naming a distribution's entry point belongs with the distribution.
"""

from attrappe.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
