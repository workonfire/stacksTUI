import unittest

from uno.enums import CardColor, CardType
from uno.game import Card, Game, Player
from uno.protocol import card_from_dict, card_to_dict, game_view_for_player, lobby_view


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


if __name__ == '__main__':
    unittest.main()
