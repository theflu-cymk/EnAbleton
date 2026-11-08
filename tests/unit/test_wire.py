"""Client framing: a nested '}' is not the end of a reply, and sends end with a newline."""

import json
import socket
import time
import unittest

from ableton_live_mcp.connection import REMOTE_COMMAND_TIMEOUTS, AbletonConnection, command_timeout

from enableton.wire import frame_socket, install, read_response


class ChunkSock:
    def __init__(self, parts):
        self.parts = [part for part in parts]
        self.timeout = None
        self.sent = b""

    def recv(self, size, flags=0):
        if flags & socket.MSG_PEEK:
            if self.parts:
                return self.parts[0][:1]
            raise TimeoutError()
        if not self.parts:
            return b""
        return self.parts.pop(0)

    def settimeout(self, value):
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def sendall(self, data):
        self.sent += data


class WireTests(unittest.TestCase):
    def test_a_split_prefix_waits_for_the_newline(self):
        payload = b'{"status":"success","result":{"n":1},"extra":2}\n'
        cut = payload.index(b"}")
        prefix, rest = payload[:cut], payload[cut:]
        self.assertTrue(prefix.endswith(b"{") or not prefix.rstrip().endswith(b"}"))
        with self.assertRaises(json.JSONDecodeError):
            json.loads(prefix)
        sock = ChunkSock([prefix, rest])
        value, unread = read_response(sock)
        self.assertEqual(value["extra"], 2)
        self.assertEqual(value["result"]["n"], 1)
        self.assertEqual(unread, b"")

    def test_a_parsable_prefix_waits_when_the_newline_is_still_queued(self):
        prefix = b'{"status":"success","result":{"n":1}}'
        self.assertIn("n", json.loads(prefix)["result"])
        sock = ChunkSock([prefix, b"\n"])
        value, unread = read_response(sock)
        self.assertEqual(value["result"]["n"], 1)
        self.assertEqual(unread, b"")
        self.assertEqual(sock.parts, [])

    def test_a_newline_returns_the_first_frame_without_idle(self):
        sock = ChunkSock([b'{"a":1}\n{"b":2}\n'])
        value, rest = read_response(sock)
        self.assertEqual(value, {"a": 1})
        self.assertEqual(rest, b'{"b":2}\n')

    def test_a_complete_object_without_a_newline_waits_until_idle(self):
        left, right = socket.socketpair()
        try:
            left.settimeout(2)
            right.sendall(b'{"status":"success","result":{"n":1}}')
            started = time.monotonic()
            value, rest = read_response(left)
            elapsed = time.monotonic() - started
        finally:
            left.close()
            right.close()
        self.assertEqual(value["result"]["n"], 1)
        self.assertEqual(rest, b"")
        self.assertGreaterEqual(elapsed, 0.04)

    def test_sendall_appends_one_newline(self):
        left, right = socket.socketpair()
        try:
            framed = frame_socket(frame_socket(left))
            framed.sendall(b'{"type":"get_session_info","params":{}}')
            framed.sendall(b"{}\n")
            right.settimeout(1)
            expected = b'{"type":"get_session_info","params":{}}\n{}\n'
            received = b""
            while len(received) < len(expected):
                received += right.recv(64)
        finally:
            left.close()
            right.close()
        self.assertEqual(received, expected)

    def test_install_extends_the_arrangement_import_budget_once(self):
        install()
        first = AbletonConnection.send_command
        install()
        self.assertIs(AbletonConnection.send_command, first)
        self.assertEqual(REMOTE_COMMAND_TIMEOUTS["create_arrangement_audio_clip"], 60.0)
        self.assertEqual(command_timeout("create_arrangement_audio_clip"), 65.0)


if __name__ == "__main__":
    unittest.main()
