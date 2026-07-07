import asyncio
import argparse
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from uno.enums import CardColor, GameEventType
from uno.exceptions import CardNotInPossessionError, CardNotPlayableError
from uno.game import Card, Game, GameEvent, Player
from uno.protocol import (
    card_from_dict,
    error_message,
    event_to_dict,
    info_message,
    lobby_view,
    state_message,
)


DEFAULT_RULES: dict[str, Any] = {
    'starting_cards': 7,
    'cheats': False,
    'card_stacking': True,
}


@dataclass
class Room:
    name: str
    rules: dict[str, Any]
    players: dict[str, Player] = field(default_factory=dict)
    connections: dict[str, Any] = field(default_factory=dict)
    announced_departures: set[str] = field(default_factory=set)
    game: Game | None = None

    @property
    def started(self) -> bool:
        return self.game is not None

    def add_player(self, name: str, websocket: Any) -> Player:
        if self.started:
            raise ValueError("This game has already started.")
        if name in self.players:
            raise ValueError("That player name is already taken in this room.")
        player = Player(name)
        self.players[name] = player
        self.connections[name] = websocket
        return player

    def remove_connection(self, websocket: Any) -> list[Player]:
        disconnected = [
            name for name, connection in self.connections.items()
            if connection == websocket
        ]
        removed_players = []
        for name in disconnected:
            del self.connections[name]
            player = self.players.pop(name, None)
            if player is not None:
                removed_players.append(player)
        return removed_players


class UnoServer:
    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.rules = DEFAULT_RULES.copy()
        self.rules.update(rules or {})
        self.rules['cheats'] = False

    async def handler(self, websocket: Any) -> None:
        room: Room | None = None
        player: Player | None = None
        try:
            join_message = await self._receive_json(websocket)
            if join_message.get('action') != 'join':
                await self._send(websocket, error_message("First message must be a join action."))
                return

            room_name = str(join_message.get('room') or 'default')
            player_name = str(join_message.get('name') or '').strip().lower()
            if not player_name:
                await self._send(websocket, error_message("Player name is required."))
                return

            room = self.rooms.setdefault(room_name, Room(room_name, self.rules.copy()))
            player = room.add_player(player_name, websocket)
            logging.info("%s joined room %s", player.name, room.name)
            await self._broadcast_room(room, info_message(f"{player.name} joined {room.name}."))
            await self._broadcast_room_state(room)

            async for raw_message in websocket:
                await self._handle_message(room, player, raw_message)
        except ValueError as error:
            await self._send(websocket, error_message(str(error)))
        except Exception:
            logging.exception("Unhandled websocket error")
            await self._send(websocket, error_message("Internal server error."))
        finally:
            if room is not None:
                removed_players = room.remove_connection(websocket)
                if removed_players:
                    for removed_player in removed_players:
                        await self._announce_player_left(room, removed_player)
                    await self._remove_players_from_game(room, removed_players)
                await self._broadcast_room_state(room)
                if not room.connections:
                    self.rooms.pop(room.name, None)

    async def _handle_message(self, room: Room, player: Player, raw_message: str) -> None:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send(room.connections[player.name], error_message("Invalid JSON."))
            return

        action = message.get('action')
        if action == 'start':
            await self._start_game(room)
        elif action == 'play':
            await self._play_card(room, player, message)
        elif action == 'draw':
            await self._draw_card(room, player)
        elif action == 'pass':
            await self._pass_turn(room, player)
        elif action == 'leave':
            await self._announce_player_left(room, player)
            await room.connections[player.name].close()
        else:
            await self._send(room.connections[player.name], error_message(f"Unknown action: {action}"))

    async def _start_game(self, room: Room) -> None:
        if room.started:
            await self._broadcast_room(room, error_message("Game has already started."))
            return
        if len(room.players) < 2:
            await self._broadcast_room(room, error_message("At least two players are required."))
            return

        room.game = Game(list(room.players.values()), room.rules.copy())
        await self._broadcast_room(room, info_message("Game started."))
        await self._broadcast_room_state(room)

    async def _play_card(self, room: Room, player: Player, message: dict[str, Any]) -> None:
        game = await self._active_game(room, player)
        if game is None:
            return
        if game.turn != player:
            await self._send(room.connections[player.name], error_message("It is not your turn."))
            return

        try:
            card = card_from_dict(message['card'])
            selected_color = None
            if card.is_wild:
                color_name = message.get('color')
                if color_name is None:
                    await self._send(room.connections[player.name], error_message("Wild cards require a color."))
                    return
                selected_color = CardColor[color_name]
            event = game.play(card, player)
            if event.type == GameEventType.AWAIT_COLOR_INPUT:
                game.stack[0] = Card(None, selected_color)
                event = GameEvent(
                    GameEventType.COLOR_CHANGED,
                    {'player': player, 'new_color': selected_color},
                )
            await self._finish_turn(room, event)
        except KeyError:
            await self._send(room.connections[player.name], error_message("Invalid card or color."))
        except (CardNotPlayableError, CardNotInPossessionError) as error:
            await self._send(room.connections[player.name], error_message(str(error)))

    async def _draw_card(self, room: Room, player: Player) -> None:
        game = await self._active_game(room, player)
        if game is None:
            return
        if game.turn != player:
            await self._send(room.connections[player.name], error_message("It is not your turn."))
            return
        game.deal_card(player)
        await self._broadcast_room(room, info_message(f"{player.name} drew a card."))
        await self._broadcast_room_state(room)

    async def _pass_turn(self, room: Room, player: Player) -> None:
        game = await self._active_game(room, player)
        if game is None:
            return
        if game.turn != player:
            await self._send(room.connections[player.name], error_message("It is not your turn."))
            return
        game.set_next_turn()
        await self._broadcast_room(room, info_message(f"{player.name} passed."))
        await self._broadcast_room_state(room)

    async def _finish_turn(self, room: Room, event: Any) -> None:
        if room.game is None:
            return
        winner = room.game.get_winner()
        if winner is not None:
            room.game.win(winner)
            await self._broadcast_room(room, info_message(f"{winner.name} won."))
        elif event.type != GameEventType.NO_EVENT:
            await self._broadcast_room(room, {'type': 'event', 'event': event_to_dict(event)})
        await self._broadcast_room_state(room)

    async def _active_game(self, room: Room, player: Player) -> Game | None:
        if room.game is None:
            await self._send(room.connections[player.name], error_message("Game has not started."))
            return None
        if not room.game.active:
            await self._send(room.connections[player.name], error_message("Game is over."))
            return None
        return room.game

    async def _broadcast_room_state(self, room: Room) -> None:
        if room.game is None:
            await self._broadcast_room(room, lobby_view(room.name, list(room.players.values()), room.rules))
            return
        for player_name, websocket in list(room.connections.items()):
            player = room.players[player_name]
            await self._send(websocket, state_message(room.game, player))

    async def _remove_players_from_game(self, room: Room, players: list[Player]) -> None:
        if room.game is None:
            return

        for player in players:
            if player not in room.game.players:
                continue
            removed_index = room.game.players.index(player)
            room.game.players.remove(player)
            if room.game.players:
                if removed_index < room.game.turn_index:
                    room.game.turn_index -= 1
                room.game.turn_index %= len(room.game.players)
            else:
                room.game.turn_index = 0

        if room.game.active and len(room.game.players) < 2:
            room.game.end()
            await self._broadcast_room(room, info_message("Game ended because fewer than two players remain."))

    async def _announce_player_left(self, room: Room, player: Player) -> None:
        if player.name in room.announced_departures:
            return
        room.announced_departures.add(player.name)
        logging.info("%s left room %s", player.name, room.name)
        await self._broadcast_room(room, info_message(f"{player.name} left {room.name}."))

    async def _broadcast_room(self, room: Room, message: dict[str, Any]) -> None:
        await asyncio.gather(
            *(self._send(websocket, message) for websocket in list(room.connections.values())),
            return_exceptions=True,
        )

    async def _send(self, websocket: Any, message: dict[str, Any]) -> None:
        await websocket.send(json.dumps(message))

    async def _receive_json(self, websocket: Any) -> dict[str, Any]:
        return json.loads(await websocket.recv())


async def serve(host: str = '127.0.0.1', port: int = 8765, rules: dict[str, Any] | None = None) -> None:
    try:
        import websockets
    except ImportError as error:
        raise RuntimeError("Install the 'websockets' package to run the UNO server.") from error

    server = UnoServer(rules)
    async with websockets.serve(server.handler, host, port):
        logging.info("UNO server listening on ws://%s:%s", host, port)
        await asyncio.Future()


def main() -> None:
    argparser = argparse.ArgumentParser()
    argparser.add_argument('--host', default='127.0.0.1')
    argparser.add_argument('--port', type=int, default=8765)
    argparser.add_argument('--starting-cards', type=int, default=DEFAULT_RULES['starting_cards'])
    argparser.add_argument('--disable-card-stacking', action='store_true')
    arguments = argparser.parse_args()
    if arguments.starting_cards <= 1:
        raise SystemExit("Starting cards can't be lower than 2.")

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    asyncio.run(serve(
        arguments.host,
        arguments.port,
        {
            'starting_cards': arguments.starting_cards,
            'card_stacking': not arguments.disable_card_stacking,
        },
    ))
