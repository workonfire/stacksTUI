import asyncio
import json
import unittest

from uno.game import Game, Player
from uno.server import Room, UnoServer


class RecordingWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send(self, message):
        self.messages.append(json.loads(message))

    async def close(self):
        self.closed = True


class ServerTest(unittest.TestCase):
    def test_remove_connection_removes_player_from_room(self):
        room = Room("test", {'starting_cards': 3, 'cheats': False, 'card_stacking': False})
        websocket = object()
        player = Player("alice")
        room.players[player.name] = player
        room.connections[player.name] = websocket

        removed_players = room.remove_connection(websocket)

        self.assertEqual(removed_players, [player])
        self.assertEqual(room.players, {})
        self.assertEqual(room.connections, {})

    def test_game_ends_when_less_than_two_players_remain(self):
        rules = {'starting_cards': 3, 'cheats': False, 'card_stacking': False}
        server = UnoServer(rules)
        room = Room("test", rules)
        alice = Player("alice")
        bob = Player("bob")
        room.players = {alice.name: alice}
        room.game = Game([alice, bob], rules)

        asyncio.run(server._remove_players_from_game(room, [bob]))

        self.assertEqual(room.game.players, [alice])
        self.assertFalse(room.game.active)

    def test_leave_broadcasts_info_to_every_connected_player(self):
        rules = {'starting_cards': 3, 'cheats': False, 'card_stacking': False}
        server = UnoServer(rules)
        room = Room("test", rules)
        alice = Player("alice")
        bob = Player("bob")
        alice_socket = RecordingWebSocket()
        bob_socket = RecordingWebSocket()
        room.players = {alice.name: alice, bob.name: bob}
        room.connections = {alice.name: alice_socket, bob.name: bob_socket}

        asyncio.run(server._handle_message(room, alice, '{"action": "leave"}'))

        self.assertTrue(alice_socket.closed)
        self.assertEqual(alice_socket.messages[0], {'type': 'info', 'message': 'alice left test.'})
        self.assertEqual(bob_socket.messages[0], {'type': 'info', 'message': 'alice left test.'})

    def test_departure_announcement_is_not_duplicated(self):
        rules = {'starting_cards': 3, 'cheats': False, 'card_stacking': False}
        server = UnoServer(rules)
        room = Room("test", rules)
        alice = Player("alice")
        bob = Player("bob")
        bob_socket = RecordingWebSocket()
        room.players = {bob.name: bob}
        room.connections = {bob.name: bob_socket}

        asyncio.run(server._announce_player_left(room, alice))
        asyncio.run(server._announce_player_left(room, alice))

        self.assertEqual(len(bob_socket.messages), 1)
        self.assertEqual(bob_socket.messages[0], {'type': 'info', 'message': 'alice left test.'})

    def test_departure_announcement_is_logged_on_server(self):
        rules = {'starting_cards': 3, 'cheats': False, 'card_stacking': False}
        server = UnoServer(rules)
        room = Room("test", rules)

        with self.assertLogs(level='INFO') as logs:
            asyncio.run(server._announce_player_left(room, Player("alice")))

        self.assertIn("INFO:root:alice left room test", logs.output)

    def test_leave_is_announced_before_game_is_ended(self):
        rules = {'starting_cards': 3, 'cheats': False, 'card_stacking': False}
        server = UnoServer(rules)
        room = Room("test", rules)
        alice = Player("alice")
        bob = Player("bob")
        bob_socket = RecordingWebSocket()
        room.players = {bob.name: bob}
        room.connections = {bob.name: bob_socket}
        room.game = Game([alice, bob], rules)

        removed_players = [alice]
        async def remove_player():
            for removed_player in removed_players:
                await server._announce_player_left(room, removed_player)
            await server._remove_players_from_game(room, removed_players)

        asyncio.run(remove_player())

        self.assertEqual(bob_socket.messages[0], {'type': 'info', 'message': 'alice left test.'})
        self.assertEqual(
            bob_socket.messages[1],
            {'type': 'info', 'message': 'Game ended because fewer than two players remain.'},
        )


if __name__ == '__main__':
    unittest.main()
