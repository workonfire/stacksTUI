import asyncio
import contextlib
import json
import logging
import sys
from typing import Any

from rich.console import Console

from uno.enums import CardColor
from uno.game import Card
from uno.protocol import card_from_dict, card_to_dict


console = Console(color_system='standard')


class ServerDisconnectedError(Exception):
    ...


class ClientQuitError(Exception):
    ...


class NetworkClient:
    def __init__(
        self,
        uri: str,
        name: str,
        room: str,
    ) -> None:
        self.uri = uri
        self.name = name.lower()
        self.room = room
        self.latest_state: dict[str, Any] | None = None
        self.latest_lobby: dict[str, Any] | None = None
        self.in_lobby = True
        self.active = True

    async def run(self) -> None:
        try:
            import websockets
            from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
        except ImportError as error:
            raise RuntimeError("Install the 'websockets' package to use network multiplayer.") from error

        try:
            async with websockets.connect(self.uri) as websocket:
                await self._send(websocket, {
                    'action': 'join',
                    'name': self.name,
                    'room': self.room,
                })
                input_task = asyncio.create_task(self._input_loop(websocket))
                try:
                    await self._receive_loop(websocket)
                except ConnectionClosed as error:
                    self._exit_disconnected(error)
                except ServerDisconnectedError:
                    self._exit_disconnected()
                finally:
                    self.active = False
                    input_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, ServerDisconnectedError):
                        await input_task
        except KeyboardInterrupt as error:
            self.active = False
            raise SystemExit from error
        except ClientQuitError:
            self.active = False
            raise SystemExit
        except ServerDisconnectedError:
            self._exit_disconnected()
        except InvalidURI:
            console.print(f"[bright_red]Invalid server address: {self.uri}[/bright_red]")
        except InvalidHandshake:
            console.print("[bright_red]The server rejected the WebSocket connection.[/bright_red]")
        except OSError as error:
            console.print(f"[bright_red]Could not connect to {self.uri}: {error}[/bright_red]")

    async def _receive_loop(self, websocket: Any) -> None:
        async for raw_message in websocket:
            try:
                await self._handle_message(raw_message)
            except json.JSONDecodeError:
                console.print("[bright_red]Server sent an invalid message.[/bright_red]")
                logging.debug("Invalid server message: %r", raw_message)
            if not self.active:
                break
        if self.active:
            raise ServerDisconnectedError

    async def _input_loop(self, websocket: Any) -> None:
        while True:
            try:
                text = await self._read_line("> ")
            except (EOFError, KeyboardInterrupt) as error:
                self.active = False
                with contextlib.suppress(ServerDisconnectedError):
                    await self._send(websocket, {'action': 'leave'})
                await websocket.close()
                raise ClientQuitError from error
            text = text.strip()
            if self.in_lobby:
                if text == '/start':
                    await self._send(websocket, {'action': 'start'})
                else:
                    console.print("Type [bright_blue]/start[/bright_blue] when everyone has joined.")
                continue

            if self.latest_state is None:
                continue
            if not self.latest_state.get('your_turn'):
                console.print("It is not your turn.")
                continue

            if text == '':
                await self._send(websocket, {'action': 'draw'})
            elif text == '/pass':
                await self._send(websocket, {'action': 'pass'})
            else:
                card = Card.from_str(text.upper())
                if card is None:
                    console.print("[bright_red]Incorrect card. Example: 7 RED[/bright_red]")
                    continue
                message: dict[str, Any] = {
                    'action': 'play',
                    'card': card_to_dict(card),
                }
                if card.is_wild:
                    color = await self._read_color()
                    message['color'] = color.name
                await self._send(websocket, message)

    async def _read_color(self) -> CardColor:
        while True:
            color_input = await self._read_line("New card color: ")
            try:
                return CardColor[color_input.strip().upper()]
            except KeyError:
                console.print("[bright_red]Incorrect color. Example: GREEN[/bright_red]")

    @staticmethod
    async def _read_line(prompt: str) -> str:
        console.print(prompt, end='')
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        def read_stdin() -> None:
            if future.done():
                return
            line = sys.stdin.readline()
            if line == '':
                future.set_exception(EOFError)
            else:
                future.set_result(line)

        loop.add_reader(sys.stdin, read_stdin)
        try:
            return await future
        finally:
            loop.remove_reader(sys.stdin)

    async def _handle_message(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        message_type = message.get('type')
        if message_type == 'lobby':
            self.in_lobby = True
            if self.latest_lobby is None:
                self._print_lobby(message)
            else:
                self._print_lobby_players(message)
            self.latest_lobby = message
        elif message_type == 'state':
            self.in_lobby = False
            self.latest_state = message['state']
            if self.latest_state.get('winner') is not None:
                self._print_winner(self.latest_state['winner'])
                self.active = False
                return
            if not self.latest_state.get('active', True):
                self.active = False
                return
            self._print_state(self.latest_state)
        elif message_type == 'error':
            console.print(f"[bright_red]{message['message']}[/bright_red]")
        elif message_type == 'info':
            console.print(f"\n[bright_blue]INFO: {message['message']}[/bright_blue]")
        elif message_type == 'event':
            self._print_event(message['event'])

    @staticmethod
    def _print_lobby(message: dict[str, Any]) -> None:
        players = ', '.join(player['name'] for player in message['players'])
        rules = message.get('rules') or {}
        console.print(f"\nRoom: [bold]{message['room']}[/bold]")
        console.print(f"Players: {players or '(none)'}")
        if rules:
            starting_cards = rules.get('starting_cards', 7)
            card_stacking = rules.get('card_stacking', True)
            console.print(
                f"Rules: {starting_cards} starting cards, "
                f"card stacking {'[green]on[/green]' if card_stacking else '[red]off[/red]'}"
            )
        console.print("Type [bright_blue]/start[/bright_blue] to begin.")

    @staticmethod
    def _print_lobby_players(message: dict[str, Any]) -> None:
        players = ', '.join(player['name'] for player in message['players'])
        console.print(f"Players: {players or '(none)'}")

    def _print_state(self, state: dict[str, Any]) -> None:
        console.print("\n- Turn: [", end='')
        for player in state['players']:
            name = player['name']
            if name == state['turn']:
                console.print(f' [bold][bright_white][underline]{name}[/underline][/bright_white][/bold]', end='')
            else:
                console.print(f' {name}', end='')
        console.print(' ]')

        console.print(
            f"\n   [ [bright_cyan]-> [bright_blue]Current card[bright_white]: "
            f"[bold][underline]{self._format_card(state['top_card'])}[/bold][/underline] "
            f"[bright_cyan]<- [/bright_cyan]]\n"
        )
        counts = ', '.join(
            f"{player['name']}: {player['cards']}"
            for player in state['players']
            if player['name'] != state['you']['name']
        )
        if counts:
            console.print(f"-- Other hands: {counts}")
        console.print(f"-- Your cards: {self._format_hand(state['you']['hand'])}\n")
        if state.get('winner') is not None:
            console.print(f"[green]Winner: {state['winner']}[/green]")
        elif state.get('your_turn'):
            console.print("Your turn. Enter a card, blank to draw, or /pass.")
            console.print("> ", end='')

    @staticmethod
    def _print_winner(winner: str) -> None:
        console.print(f"[green]Winner: {winner}[/green]")

    def _print_event(self, event: dict[str, Any]) -> None:
        if event['type'] == 'STACKING_ACTIVE':
            for card in event['payload'].get('stacked_cards', []):
                console.print(f"> Stacking {self._format_card(card)}...")
        elif event['type'] == 'COLOR_CHANGED':
            console.print(f"{event['payload'].get('player')} changed color to {event['payload'].get('new_color')}.")

    def _format_hand(self, cards: list[dict[str, str | None]]) -> str:
        return ', '.join(self._format_card(card) for card in cards)

    def _format_card(self, card: dict[str, str | None]) -> str:
        return str(card_from_dict(card))

    async def _send(self, websocket: Any, message: dict[str, Any]) -> None:
        try:
            await websocket.send(json.dumps(message))
        except Exception as error:
            if error.__class__.__name__.startswith('ConnectionClosed'):
                self.active = False
                raise ServerDisconnectedError from error
            raise

    def _exit_disconnected(self, error: Exception | None = None) -> None:
        self.active = False
        reason = getattr(error, 'reason', '')
        if reason:
            console.print(f"[bright_red]Disconnected from server: {reason}[/bright_red]")
        else:
            console.print("[bright_red]Disconnected from server.[/bright_red]")
        raise SystemExit


async def connect(
    uri: str,
    name: str,
    room: str = 'default',
) -> None:
    await NetworkClient(uri, name, room).run()
