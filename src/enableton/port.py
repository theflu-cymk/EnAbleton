"""Loopback port selection for the client and the generated bridge.

The bridge listens on one TCP port and the client connects to the same one.
The default is fixed at 9877. ``ENABLETON_PORT`` overrides it on both sides:
the generated script bakes the value in at build time, and the client maps it
onto the ``ABLETON_PORT`` variable the pinned upstream client reads at import.

A bridge built for one port cannot answer a client on another, so a mismatch is
reported rather than retried: the client would otherwise wait for a timeout.
"""

import os

DEFAULT_PORT = 9877
ENVIRONMENT_VARIABLE = "ENABLETON_PORT"
MINIMUM_PORT = 1024
MAXIMUM_PORT = 65535


def parse(value):
    """Return ``value`` as a usable loopback port, or raise ValueError."""

    text = str(value).strip()
    if not text.isdigit():
        raise ValueError(f"{ENVIRONMENT_VARIABLE} must be a whole number, not {value!r}")
    port = int(text)
    if not MINIMUM_PORT <= port <= MAXIMUM_PORT:
        raise ValueError(
            f"{ENVIRONMENT_VARIABLE} must be between {MINIMUM_PORT} and {MAXIMUM_PORT}, not {port}"
        )
    return port


def configured():
    """Return the port named by the environment, or None when it is unset."""

    raw = os.environ.get(ENVIRONMENT_VARIABLE)
    if raw is None or not raw.strip():
        return None
    return parse(raw)


def client_port():
    """Return the port this client connects to."""

    port = configured()
    return DEFAULT_PORT if port is None else port


def apply_client_environment():
    """Point the pinned upstream client at the configured port.

    ``ableton_live_mcp.connection`` reads ``ABLETON_PORT`` when it is imported,
    so this must run first. An explicit ``ENABLETON_PORT`` wins, because that is
    the variable the generated bridge is built from.
    """

    port = configured()
    if port is not None:
        os.environ["ABLETON_PORT"] = str(port)
    return client_port()
