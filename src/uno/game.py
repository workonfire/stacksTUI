import logging
import random

from uno.enums import *
from uno.exceptions import *

from typing import Any, Generator, Optional

class GameEvent:
    def __init__(self, type_: GameEventType, payload: dict[str, Any]):
        self.type: GameEventType = type_
        self.payload: dict[str, Any] = payload


# TODO: Refactor

class Card:
    def __init__(self, card_type: Optional[CardType], color: Optional[CardColor]):
        self.card_type: Optional[CardType] = card_type
        self.is_wild: bool = self.card_type in (CardType.CARD_WILDCARD, CardType.CARD_PLUS_4)
        self.is_special: bool = self.is_wild or self.card_type in (CardType.CARD_PLUS_2, CardType.CARD_REVERSE, CardType.CARD_SKIP)
        self.color: Optional[CardColor] = None if self.is_wild else color
        if not isinstance(self.card_type, CardType) and not isinstance(self.color, CardColor):
            raise InvalidCardException

    def __repr__(self) -> str:
        if self.card_type is None and self.color is not None:
            return f'* {self.color.name}'
        card_type_name: str = ' '.join(self.card_type.name.split('_')[1:]).replace('PLUS ', '+')
        # noinspection PyUnresolvedReferences
        return card_type_name if self.is_wild and self.color is None else f'{card_type_name} {self.color.name}'

    def __str__(self) -> str:
        color: str = f'[bright_{self.color.name.lower()}]' if self.color is not None else '[bright_white]'
        return color + self.__repr__() + '[bright_white]'

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Card):
            return self.card_type == other.card_type and self.color == other.color
        else:
            return NotImplemented # TODO

    @staticmethod
    def from_str(value: str) -> Optional['Card']:
        try:
            card_type, card_color = value.upper().split(' ')
            card: Optional['Card'] = Card(CardType["CARD_" + card_type.replace('+', 'PLUS_')], CardColor[card_color])
        except ValueError:
            if value.upper() == 'WILDCARD':
                card = Card(CardType.CARD_WILDCARD, None)
            elif value.upper() == '+4':
                card = Card(CardType.CARD_PLUS_4, None)
            else:
                card = None # Raise exception?
        except KeyError:
            card = None
        return card

    def playable(self, comparator: 'Card') -> bool:
        """
        Compares two cards between their types and colors.
        :param comparator: card object
        :return: true, if they're similar
        """
        return self.is_wild or self.card_type == comparator.card_type or self.color == comparator.color


class Deck:
    def draw(self, number: int = 1) -> list[Card]:
        """
        Draws a specified amount of cards.
        :param number: a number of cards that you want to draw. Default is 1.
        :return: a list of cards, if the amount is greater than 1.
        """
        return [self.stack for _ in range(number)]

    @staticmethod
    def _stack() -> Generator[Card, None, None]:
        card_type: CardType = random.choice([*CardType])
        color: CardColor = random.choice([*CardColor])
        yield Card(card_type, color)

    @property
    def stack(self) -> Card:
        return next(self._stack())


class Player:
    def __init__(self, name: str = ''):
        self.hand: list[Card] = []
        self.name: str = name
        self.is_computer: bool = 'computer' in self.name.lower() if self.name is not None else False

    def format_hand_contents(self) -> str:
        return ', '.join([card.__str__() for card in self.hand])

    def __repr__(self) -> str:
        return f'{self.name}: ' + ', '.join([str(self.hand)])


class Table:
    def __init__(self, players: list[Player], rules: dict[str, Any]):
        self.rules: dict[str, Any] = rules
        self.players: list[Player] = players
        self.deck: Deck = Deck()
        self.stack: list[Card] = self.deck.draw()
        self.turn_index: int = 0
        self.direction: int = 1
        for player in players:
            player.hand = self.deck.draw(self.rules['starting_cards'])

    @property
    def last_played_card(self) -> Card:
        return self.stack[0]

    @property
    def turn(self) -> Player:
        return self.players[self.turn_index]

    def play(self, card: Card, player: Player, stacking_active: bool = False) -> GameEvent:
        """
        Puts the selected card on top of the stack.
        :param card: card object.
        :param player: player object.
        :param stacking_active: describes if the player is currently in the middle of card-stacking.
        :return: a GameEvent object, could be NO_EVENT, AWAIT_COLOR_INPUT, COLOR_CHANGED or STACKING_ACTIVE
        """
        event: GameEvent = GameEvent(GameEventType.NO_EVENT, {})

        if card.playable(self.last_played_card):
            if card not in player.hand:
                raise CardNotInPossessionError(f"The player {player.name} does not have {card} card.")
            self.stack.insert(0, card)
            player.hand.remove(card)

            if card.is_wild:
                if self.turn.is_computer:
                    new_color: CardColor = Turn(self).most_reasonable_color
                    event = GameEvent(GameEventType.COLOR_CHANGED, {'player': self.turn, 'new_color': new_color})
                else:
                    event = GameEvent(GameEventType.AWAIT_COLOR_INPUT, {'player': self.turn}) # Is the payload needed here?
                if card.card_type == CardType.CARD_PLUS_4:
                    next_player: Player = self.players[(self.turn_index + self.direction) % len(self.players)]
                    new_cards: list[Card] = self.deck.draw(4)
                    next_player.hand.extend(new_cards)
                logging.debug(f"Card on stack: {self.stack[0]}")
            else:
                if card.card_type == CardType.CARD_PLUS_2:  # TODO: Queue +2 and +4 stacking
                    next_player = self.players[(self.turn_index + self.direction) % len(self.players)]
                    new_cards = self.deck.draw(2)
                    next_player.hand.extend(new_cards)
                if self.rules.get('card_stacking') and not stacking_active:
                    stacked_cards: list[Card] = []
                    for playable_card in Turn(self).playable_cards:
                        if not playable_card.is_wild and playable_card.card_type == self.last_played_card.card_type:
                            self.play(playable_card, player, stacking_active=True)
                            stacked_cards.append(playable_card)
                            # TODO: +2 and/or +4 stacking
                    event = GameEvent(GameEventType.STACKING_ACTIVE, {'stacked_cards': stacked_cards})
            if not stacking_active:
                if card.card_type == CardType.CARD_SKIP:
                    self.skip_next_player()
                elif card.card_type == CardType.CARD_REVERSE:
                    if len(self.players) > 2:
                        self.reverse_queue()
                        self.set_next_turn()
                else:
                    self.set_next_turn()
        else:
            raise CardNotPlayableError(f"The player {player.name} cannot play with {card}.")
        return event

    def deal_card(self, player: Player, amount: int = 1):
        """
        Gives the player a card from the deck.
        """
        cards = self.deck.draw(amount)
        player.hand.extend(cards)

    @property
    def next_turn(self) -> Player:
        return self.players[(self.turn_index + self.direction) % len(self.players)]

    def set_next_turn(self):
        self.turn_index = (self.turn_index + self.direction) % len(self.players)

    def reverse_queue(self):
        self.direction *= -1

    def skip_next_player(self):
        self.turn_index = (self.turn_index + self.direction) % len(self.players)
        self.set_next_turn()

class Game(Table):
    def __init__(self, players: list[Player], rules: dict[str, Any]):
        super().__init__(players, rules)
        self.active: bool = True
        self.winner: Player | None = None
        while self.last_played_card.is_special:
            self.stack = self.deck.draw()

    def end(self):
        """
        Ends the game and sets its status to inactive.
        """
        if not self.active:
            raise RuntimeError("The game is already inactive.")
        self.active: bool = False

    def get_winner(self) -> Optional[Player]:
        """
        Checks if somebody has won the game.
        """
        for player in self.players:
            if not player.hand:
                return player
        return None

    def win(self, player: Player):
        """
        Sets the game winner and ends it.
        :param player: player object
        """
        if self.winner is not None:
            raise WinnerAlreadySetException("The winner has already been set.")
        self.winner = player
        self.end()


class Turn:
    def __init__(self, table: Table):
        self.table: Table = table
        self.last_card: Card = self.table.last_played_card
        self.hand: list[Card] = self.table.turn.hand

    @property
    def playable_cards(self) -> list[Card]:
        playable_cards: list[Card] = []
        for card in self.hand:
            if card.playable(self.last_card):
                playable_cards.append(card)
        return playable_cards

    @property
    def most_reasonable_color(self) -> CardColor:
        card_colors: list[Optional[CardColor]] = [card.color for card in self.playable_cards]
        if not card_colors or set(card_colors) == {None}:
            return random.choice([*CardColor])
        return max(set(card_colors), key=card_colors.count)

    def get_result(self) -> Card:
        while not self.playable_cards:
            self.table.deal_card(self.table.turn)
        return random.choice(self.playable_cards)
