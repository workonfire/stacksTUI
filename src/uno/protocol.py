from typing import Any

from uno.enums import CardColor, CardType, GameEventType
from uno.game import Card, Game, GameEvent, Player


def card_to_dict(card: Card) -> dict[str, str | None]:
    return {
        'type': card.card_type.name if card.card_type is not None else None,
        'color': card.color.name if card.color is not None else None,
    }


def card_from_dict(data: dict[str, str | None]) -> Card:
    card_type = CardType[data['type']] if data.get('type') is not None else None
    color = CardColor[data['color']] if data.get('color') is not None else None
    return Card(card_type, color)


def event_to_dict(event: GameEvent) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in event.payload.items():
        if isinstance(value, CardColor):
            payload[key] = value.name
        elif isinstance(value, Player):
            payload[key] = value.name
        elif isinstance(value, list) and all(isinstance(item, Card) for item in value):
            payload[key] = [card_to_dict(item) for item in value]
        else:
            payload[key] = value
    return {'type': event.type.name, 'payload': payload}


def player_public_view(player: Player) -> dict[str, Any]:
    return {
        'name': player.name,
        'cards': len(player.hand),
        'is_computer': player.is_computer,
    }


def game_view_for_player(game: Game, player: Player) -> dict[str, Any]:
    winner = game.get_winner()
    return {
        'active': game.active,
        'winner': winner.name if winner is not None else None,
        'you': {
            'name': player.name,
            'hand': [card_to_dict(card) for card in player.hand],
        },
        'players': [player_public_view(table_player) for table_player in game.players],
        'turn': game.turn.name,
        'your_turn': game.turn == player,
        'top_card': card_to_dict(game.last_played_card),
        'direction': game.direction,
        'rules': game.rules,
    }


def lobby_view(room_name: str, players: list[Player], rules: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'type': 'lobby',
        'room': room_name,
        'players': [player_public_view(player) for player in players],
        'rules': rules or {},
    }


def state_message(game: Game, player: Player) -> dict[str, Any]:
    return {
        'type': 'state',
        'state': game_view_for_player(game, player),
    }


def error_message(message: str) -> dict[str, str]:
    return {'type': 'error', 'message': message}


def info_message(message: str) -> dict[str, str]:
    return {'type': 'info', 'message': message}
