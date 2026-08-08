"""An instrument emulator that answers a measurement driver over a socket.

This package is layout only. No behaviour lives here yet. The subpackages are
named ahead of the work so that later changes land in one structure rather than
inventing three.

``scpi`` parses and dispatches the message language. ``device`` holds the
instrument model and its state. ``transport`` owns the listener and the
sessions. ``impairment`` holds the physical and failure behaviour. ``profile``
loads and validates a device profile.
"""

__version__  =  "0.1.0"

__all__ = ["__version__"]
