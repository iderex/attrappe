"""The listener and the sessions a client connects to.

`session` is the emulator with no socket underneath it, which is the in-process
transport `docs/decisions/0002-transport.md` names beside the socket: one
instrument, one seed, its own named streams and its own operation counter.

`server` is the socket surface. It binds to loopback unless told otherwise,
frames on the configured terminator, refuses a message that will not fit rather
than growing without bound, and hands every connection a session of its own.
"""

from attrappe.transport.server import (
    DEFAULT_MAXIMUM_MESSAGE,
    DEFAULT_PORT,
    DEFAULT_TERMINATOR,
    ENCODING,
    LOOPBACK,
    Connection,
    Server,
)
from attrappe.transport.session import Session, choose_seed, stream_seed

__all__ = [
    "DEFAULT_MAXIMUM_MESSAGE",
    "DEFAULT_PORT",
    "DEFAULT_TERMINATOR",
    "ENCODING",
    "LOOPBACK",
    "Connection",
    "Server",
    "Session",
    "choose_seed",
    "stream_seed",
]
