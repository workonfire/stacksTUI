import asyncio
import contextlib
import json
from typing import Any

from rich.console import Console

from uno.enums import CardColor
from uno.game import Card
from uno.protocol import card_to_dict


console = Console(color_system='standard')


class NetworkClient:
    def __init__(
        self,
        uri: str,
        name: str,
        room: str,
        starting_cards: int = 7,
        card_stacking: bool = True,
    ) -> None:
        self.uri = uri
        self.name = name.lower()
        self.room = room
        self.starting_cards = starting_cards
        self.card_stacking = card_stacking
        self.latest_state: dict[str, Any] | None = None
        self.in_lobby = True
        self.active = True

    async def run(self) -> None:
        try:
            import websockets
        except ImportError as error:
            raise RuntimeError("Install the 'websockets' package to use network multiplayer.") from error

        async with websockets.connect(self.uri) as websocket:
            await self._send(websocket, {
                'action': 'join',
                'name': self.name,
                'room': self.room,
            })
            input_task = asyncio.create_task(self._input_loop(websocket))
            try:
                async for raw_message in websocket:
                    await self._handle_message(raw_message)
                    if not self.active:
                        break
            finally:
                input_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await input_task

    async def _input_loop(self, websocket: Any) -> None:
        while True:
            text = await asyncio.to_thread(console.input, "> ")
            text = text.strip()
            if self.in_lobby:
                if text == '/start':
                    await self._send(websocket, {
                        'action': 'start',
                        'rules': {
                            'starting_cards': self.starting_cards,
                            'card_stacking': self.card_stacking,
                        },
                    })
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
            color_input = await asyncio.to_thread(console.input, "New card color: ")
            try:
                return CardColor[color_input.strip().upper()]
            except KeyError:
                console.print("[bright_red]Incorrect color. Example: GREEN[/bright_red]")

    async def _handle_message(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        message_type = message.get('type')
        if message_type == 'lobby':
            self.in_lobby = True
            self._print_lobby(message)
        elif message_type == 'state':
            self.in_lobby = False
            self.latest_state = message['state']
            self._print_state(self.latest_state)
            if self.latest_state.get('winner') is not None:
                self.active = False
        elif message_type == 'error':
            console.print(f"[bright_red]{message['message']}[/bright_red]")
        elif message_type == 'info':
            console.print(f"[bright_blue]{message['message']}[/bright_blue]")
        elif message_type == 'event':
            self._print_event(message['event'])

    def _print_lobby(self, message: dict[str, Any]) -> None:
        players = ', '.join(player['name'] for player in message['players'])
        console.print(f"\nRoom: [bold]{message['room']}[/bold]")
        console.print(f"Players: {players or '(none)'}")
        console.print("Type [bright_blue]/start[/bright_blue] to begin.")

    def _print_state(self, state: dict[str, Any]) -> None:
        console.print("\n- Turn: [", end='')
        for player in state['players']:
            name = player['name']
            if name == state['turn']:
                console.print(f' [bold][bright_white][underline]{name}[/underline][/bright_white][/bold]', end='')
            else:
                console.print(f' {name}', end='')
        console.print(' ]')

        console.print(f"Current card: [bold]{self._format_card(state['top_card'])}[/bold]")
        counts = ', '.join(
            f"{player['name']}: {player['cards']}"
            for player in state['players']
            if player['name'] != state['you']['name']
        )
        if counts:
            console.print(f"Other hands: {counts}")
        console.print(f"Your cards: {self._format_hand(state['you']['hand'])}")
        if state.get('winner') is not None:
            console.print(f"[green]Winner: {state['winner']}[/green]")
        elif state.get('your_turn'):
            console.print("Your turn. Enter a card, blank to draw, or /pass.")

    def _print_event(self, event: dict[str, Any]) -> None:
        if event['type'] == 'STACKING_ACTIVE':
            for card in event['payload'].get('stacked_cards', []):
                console.print(f"> Stacking {self._format_card(card)}...")
        elif event['type'] == 'COLOR_CHANGED':
            console.print(f"{event['payload'].get('player')} changed color to {event['payload'].get('new_color')}.")

    def _format_hand(self, cards: list[dict[str, str | None]]) -> str:
        return ', '.join(self._format_card(card) for card in cards)

    def _format_card(self, card: dict[str, str | None]) -> str:
        card_type = card.get('type')
        color = card.get('color')
        if card_type is None and color is not None:
            return f"* {color}"
        name = ' '.join(str(card_type).split('_')[1:]).replace('PLUS ', '+')
        return name if color is None else f"{name} {color}"

    async def _send(self, websocket: Any, message: dict[str, Any]) -> None:
        await websocket.send(json.dumps(message))


async def connect(
    uri: str,
    name: str,
    room: str = 'default',
    starting_cards: int = 7,
    card_stacking: bool = True,
) -> None:
    await NetworkClient(uri, name, room, starting_cards, card_stacking).run()
