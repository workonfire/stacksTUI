import asyncio
import json
import sys
import types
import unittest

rich_module = types.ModuleType("rich")
rich_console_module = types.ModuleType("rich.console")


class ConsoleFake:
    messages = []

    def __init__(self, *args, **kwargs):
        ...

    def print(self, *args, **kwargs):
        self.messages.append(args)

    def input(self, *args, **kwargs):
        return ""


rich_console_module.Console = ConsoleFake
sys.modules.setdefault("rich", rich_module)
sys.modules.setdefault("rich.console", rich_console_module)

from uno.client import ClientQuitError, NetworkClient, ServerDisconnectedError


class ConnectionClosedFake(Exception):
    ...


class ClosedWebSocket:
    async def send(self, message):
        raise ConnectionClosedFake


class RecordingWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send(self, message):
        self.messages.append(message)

    async def close(self):
        self.closed = True


class ClientTest(unittest.TestCase):
    def setUp(self):
        ConsoleFake.messages = []

    def test_send_marks_client_inactive_when_connection_is_closed(self):
        client = NetworkClient("ws://example.invalid", "alice", "test")

        with self.assertRaises(ServerDisconnectedError):
            asyncio.run(client._send(ClosedWebSocket(), {'action': 'draw'}))

        self.assertFalse(client.active)

    def test_disconnected_message_exits_client(self):
        client = NetworkClient("ws://example.invalid", "alice", "test")

        with self.assertRaises(SystemExit):
            client._exit_disconnected()

        self.assertFalse(client.active)
        self.assertIn("Disconnected from server.", ConsoleFake.messages[0][0])

    def test_keyboard_interrupt_sends_leave_and_closes_websocket(self):
        client = NetworkClient("ws://example.invalid", "alice", "test")
        websocket = RecordingWebSocket()

        async def raise_keyboard_interrupt(prompt):
            raise KeyboardInterrupt

        client._read_line = raise_keyboard_interrupt

        with self.assertRaises(ClientQuitError):
            asyncio.run(client._input_loop(websocket))

        self.assertFalse(client.active)
        self.assertTrue(websocket.closed)
        self.assertEqual(websocket.messages, ['{"action": "leave"}'])

    def test_inactive_state_does_not_print_full_state(self):
        client = NetworkClient("ws://example.invalid", "alice", "test")
        printed_states = []
        client._print_state = printed_states.append

        asyncio.run(client._handle_message(json.dumps({
            'type': 'state',
            'state': {
                'active': False,
                'winner': None,
            },
        })))

        self.assertFalse(client.active)
        self.assertEqual(printed_states, [])

    def test_winner_state_prints_winner_without_full_state(self):
        client = NetworkClient("ws://example.invalid", "alice", "test")
        printed_states = []
        printed_winners = []
        client._print_state = printed_states.append
        client._print_winner = printed_winners.append

        asyncio.run(client._handle_message(json.dumps({
            'type': 'state',
            'state': {
                'active': False,
                'winner': 'alice',
            },
        })))

        self.assertFalse(client.active)
        self.assertEqual(printed_states, [])
        self.assertEqual(printed_winners, ['alice'])


if __name__ == '__main__':
    unittest.main()
