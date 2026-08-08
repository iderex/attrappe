"""Loading and validating a device profile.

`loader` reads a profile directory, refuses a bad declaration with every problem
it found, and constructs the identification response, the command tree, the
parameter table and the error-queue depth. The optional Python half of a profile
is executed only by `load_code_half`, never by `load_profile`.
"""

from attrappe.profile.loader import (
    CODE_FILE,
    DECLARATIVE_FILE,
    Node,
    Parameter,
    Problem,
    Profile,
    ProfileError,
    load_code_half,
    load_profile,
    main,
)

__all__ = [
    "CODE_FILE",
    "DECLARATIVE_FILE",
    "Node",
    "Parameter",
    "Problem",
    "Profile",
    "ProfileError",
    "load_code_half",
    "load_profile",
    "main",
]
