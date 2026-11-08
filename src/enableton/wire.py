"""Newline framing and the arrangement-import timeout on the upstream socket client.

The pinned 1.8.1 client treats a JSON prefix that parses as the whole reply.
Bridges from ext.14 append a newline to every response. This module patches
the client in-process: outgoing commands end with a newline, and a newline in
the reply ends the frame immediately. A bridge that does not send one is still
accepted after a short idle peek, so ext.1 through ext.13 keep answering.
Site-packages are not edited.
"""

import json
import socket

from ableton_live_mcp.connection import REMOTE_COMMAND_TIMEOUTS, AbletonConnection

_IDLE_S = 0.05
_INSTALLED = False


class _FramedSocket:
    """Proxy a socket. ``socket.sendall`` is read-only, so it cannot be replaced."""

    def __init__(self, sock):
        object.__setattr__(self, "_sock", sock)

    def sendall(self, data, *args, **kwargs):
        if isinstance(data, (bytes, bytearray)) and not data.endswith(b"\n"):
            data = bytes(data) + b"\n"
        return self._sock.sendall(data, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._sock, name)


def frame_socket(sock):
    """Return a socket whose sendall appends one newline. Idempotent."""
    if sock is None or isinstance(sock, _FramedSocket):
        return sock
    return _FramedSocket(sock)


def _peer_idle(sock, idle_s):
    """True when nothing more is readable. An empty peek means the peer closed."""
    previous = sock.gettimeout()
    try:
        sock.settimeout(idle_s)
        try:
            peeked = sock.recv(1, socket.MSG_PEEK)
        except (TimeoutError, BlockingIOError, InterruptedError):
            return True
        return peeked == b""
    finally:
        sock.settimeout(previous)


def _complete_value(data):
    """``(True, value)`` when one JSON value consumes the buffer."""
    if not data:
        return False, None
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        return False, None
    try:
        value, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return False, None
    if text[end:].strip():
        return False, None
    return True, value


def read_response(sock, buffer_size=8192, pending=b"", idle_s=_IDLE_S):
    """Return ``(value, unread)`` for one reply.

    A newline ends the frame with no idle wait. Without a newline, a buffer
    is accepted only when one JSON value consumes it and a short peek shows
    no further bytes. That still races if an old bridge's next chunk arrives
    after the peek. A new bridge puts the newline in the same sendall.
    """
    data = bytearray(pending)
    while True:
        newline = data.find(b"\n")
        if newline != -1:
            line = bytes(data[:newline])
            rest = bytes(data[newline + 1 :])
            if not rest.strip():
                rest = b""
            return json.loads(line.decode("utf-8")), rest
        found, value = _complete_value(data)
        if found and _peer_idle(sock, idle_s):
            return value, b""
        chunk = sock.recv(buffer_size)
        if not chunk:
            if not data:
                raise ConnectionError("Connection closed before receiving any data")
            raise ConnectionError("Connection closed mid-response (incomplete JSON)")
        data.extend(chunk)


def install():
    """Patch command budgets and socket framing. Safe to call more than once."""
    global _INSTALLED
    REMOTE_COMMAND_TIMEOUTS["create_arrangement_audio_clip"] = 60.0
    if _INSTALLED:
        return
    original_connect = AbletonConnection.connect
    original_send = AbletonConnection.send_command

    def connect(self):
        ok = original_connect(self)
        self.sock = frame_socket(self.sock)
        return ok

    def send_command(self, command_type, params=None):
        self.sock = frame_socket(self.sock)
        return original_send(self, command_type, params)

    def receive_full_response(self, buffer_size=8192):
        pending = getattr(self, "_enableton_pending", b"")
        response, rest = read_response(self.sock, buffer_size, pending)
        self._enableton_pending = rest
        return response

    AbletonConnection.connect = connect
    AbletonConnection.send_command = send_command
    AbletonConnection.receive_full_response = receive_full_response
    _INSTALLED = True
