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
from uno.game import *
from uno.protocol import card_from_dict, card_to_dict, game_view_for_player, lobby_view
from uno.server import Room, UnoServer


class ConnectionClosedFake(Exception):
    ...


class ClosedWebSocket:
    async def send(self, message):
        raise ConnectionClosedFake


class ClientRecordingWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send(self, message):
        self.messages.append(message)

    async def close(self):
        self.closed = True


class ServerRecordingWebSocket:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send(self, message):
        self.messages.append(json.loads(message))

    async def close(self):
        self.closed = True


class GameEngineTest(unittest.TestCase):
    def test_card(self):
        card: Card = Card(CardType.CARD_PLUS_2, CardColor.YELLOW)
        second_card: Card = Card(CardType.CARD_5, CardColor.RED)
        self.assertEqual(card.playable(second_card), False)

        card = Card(CardType.CARD_PLUS_4, None)
        second_card = Card(CardType.CARD_PLUS_4, None)
        self.assertEqual(card.playable(second_card), True)

        card = Card(CardType.CARD_PLUS_4, None)
        second_card = Card(CardType.CARD_4, CardColor.BLUE)
        self.assertEqual(card.playable(second_card), True)

        card = Card(CardType.CARD_6, CardColor.GREEN)
        second_card = Card(CardType.CARD_WILDCARD, None)
        self.assertEqual(second_card.playable(card), True)

        card = Card(None, CardColor.GREEN)
        second_card = Card(CardType.CARD_WILDCARD, None)
        self.assertEqual(second_card.playable(card), True)

        card = Card(CardType.CARD_WILDCARD, None)
        second_card = Card(CardType.CARD_7, CardColor.GREEN)
        self.assertEqual(second_card.playable(card), False)

        card = Card(None, CardColor.GREEN)
        second_card = Card(CardType.CARD_7, CardColor.YELLOW)
        self.assertEqual(second_card.playable(card), False)

    def test_card_creation(self):
        self.assertEqual(Card(CardType.CARD_6, CardColor.RED).__repr__(), "6 RED")
        self.assertEqual(Card(CardType.CARD_WILDCARD, None).__repr__(), "WILDCARD")
        self.assertEqual(Card(CardType.CARD_PLUS_4, CardColor.GREEN).__repr__(), "+4")
        self.assertEqual(Card(None, CardColor.GREEN).__repr__(), "* GREEN")
        with self.assertRaises(InvalidCardException):
            self.assertEqual(Card(None, None).__repr__(), "* GREEN")
            self.assertEqual(Card('test', 'test').__repr__(), "* GREEN")

    def test_card_from_str(self):
        self.assertEqual(Card.from_str('6 BLUE'), Card(CardType.CARD_6, CardColor.BLUE))
        self.assertEqual(Card.from_str('69 GREEN'), None)
        self.assertEqual(Card.from_str('hello'), None)
        self.assertEqual(Card.from_str('3 HELLOW'), None)
        self.assertEqual(Card.from_str('WILDCARD'), Card(CardType.CARD_WILDCARD, None))
        self.assertEqual(Card.from_str('+4'), Card(CardType.CARD_PLUS_4, None))

    def test_wildcard(self):
        for _ in range(50):
            self.assertEqual(Card(CardType.CARD_WILDCARD, CardColor.GREEN).color, None)
            self.assertEqual(Card(CardType.CARD_WILDCARD, CardColor.BLUE).card_type, CardType.CARD_WILDCARD)

        wildcard: Card = Card(CardType.CARD_WILDCARD, None)
        self.assertEqual(wildcard.is_wild, True)
        second_wildcard: Card = Card(CardType.CARD_PLUS_4, None)
        self.assertEqual(second_wildcard.is_wild, True)
        not_wildcard: Card = Card(CardType.CARD_4, CardColor.RED)
        self.assertEqual(not_wildcard.is_wild, False)

        self.assertEqual(Card(CardType.CARD_WILDCARD, None), Card(CardType.CARD_WILDCARD, None))
        self.assertEqual(
            Card(CardType.CARD_6, None).is_wild,
            Card(CardType.CARD_WILDCARD, None) in (CardType.CARD_WILDCARD, CardType.CARD_PLUS_4)
        )

    def test_deck(self):
        deck: Deck = Deck()
        deck.draw(10)
        self.assertEqual(len(deck.draw(100)), 100)

    def test_player(self):
        player: Player = Player("Computer")
        self.assertEqual(player.name, 'Computer')
        self.assertEqual(player.hand, [])
        self.assertEqual(player.is_computer, True)

    def test_player_deal(self):
        player: Player = Player("Test")
        player.hand = [Card(CardType.CARD_5, CardColor.GREEN), Card(CardType.CARD_6, CardColor.YELLOW)]
        new_cards: list[Card] = Deck().draw(5)
        for card in new_cards:
            player.hand.append(card)
        self.assertEqual(len(player.hand), 7)

    def test_table(self):
        # Creating a table
        players: list[Player] = [Player("Human"), Player("Computer")]
        rules: dict[str, Any] = {'card_stacking': False,
                                 'starting_cards': 10}
        table: Table = Table(players, rules)

        # Giving all players an initial set of cards
        try:
            # Trying to play a random card and checking the deck size
            card: Card = random.choice(table.turn.hand)
            table.play(card, table.turn)
            self.assertEqual(len(table.stack), 2)
        except CardNotPlayableError:
            self.assertEqual(len(table.stack), 1)

        self.assertEqual(type(table.turn), Player)

    def test_queue_order_starting_with_human(self):
        table: Table = Table(
            [Player("Human1"), Player("Computer1"), Player("Human2"), Player("Human3"), Player("Computer2")],
            {'card_stacking': True,
             'starting_cards': 10}
        )
        for i in range(10):
            # print(f"Current turn: {table.turn.name}. Next turn...")
            table.set_next_turn()

        table.reverse_queue()
        table.set_next_turn()
        table.set_next_turn()

        self.assertEqual(table.turn.name, "Human3")

    def test_queue_order_starting_with_computer(self):
        table: Table = Table(
            [Player("Computer1"), Player("Computer2"), Player("Human1"), Player("Human2"), Player("Human3")],
            {'card_stacking': True,
             'starting_cards': 10}
        )
        for i in range(10):
            # print(f"Current turn: {table.turn.name}. Next turn...")
            table.set_next_turn()

        table.reverse_queue()
        table.set_next_turn()
        table.set_next_turn()

        self.assertEqual(table.turn.name, "Human2")


class ProtocolTest(unittest.TestCase):
    def test_card_round_trip(self):
        card = Card(CardType.CARD_7, CardColor.RED)

        self.assertEqual(card_from_dict(card_to_dict(card)), card)

    def test_game_view_hides_other_hands(self):
        alice = Player("alice")
        bob = Player("bob")
        game = Game([alice, bob], {'starting_cards': 3, 'cheats': False, 'card_stacking': False})

        view = game_view_for_player(game, alice)

        self.assertEqual(len(view['you']['hand']), 3)
        self.assertEqual(view['players'][0]['cards'], 3)
        self.assertEqual(view['players'][1]['cards'], 3)
        self.assertNotIn('hand', view['players'][1])

    def test_lobby_view_includes_server_rules(self):
        rules = {'starting_cards': 5, 'cheats': False, 'card_stacking': False}

        view = lobby_view("test", [Player("alice")], rules)

        self.assertEqual(view['rules'], rules)


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
        websocket = ClientRecordingWebSocket()

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
        alice_socket = ServerRecordingWebSocket()
        bob_socket = ServerRecordingWebSocket()
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
        bob_socket = ServerRecordingWebSocket()
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
        bob_socket = ServerRecordingWebSocket()
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
