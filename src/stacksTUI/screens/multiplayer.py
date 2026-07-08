import asyncio
import contextlib
import json
from typing import Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, OptionList, RichLog, Static

from stacksTUI._version import _LOGO
from stackslib.enums import CardColor
from stackslib.game import Card
from stackslib.protocol import card_from_dict, card_to_dict
from stacksTUI.screens.rendering import hand_text


class MultiplayerSetupScreen(Screen):
    CSS_PATH = "../css/setup.tcss"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="setup-outer"):
            with VerticalScroll(id="setup-layout"):
                yield Static(_LOGO, markup=True, id="logo")
                yield Label("--- multiplayer ---", id="setup-title")
                with Vertical(classes="field-group"):
                    yield Label("server", classes="option-label")
                    yield Input(value="ws://127.0.0.1:8765", id="server-uri")
                with Horizontal(id="settings-row"):
                    with Vertical(classes="field-group"):
                        yield Label("name", classes="option-label")
                        yield Input(placeholder="player", id="player-name")
                    with Vertical(classes="field-group"):
                        yield Label("room", classes="option-label")
                        yield Input(value="default", id="room-name")
                yield OptionList("connect", id="connect-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#server-uri", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        match event.input.id:
            case "server-uri":
                self.query_one("#player-name", Input).focus()
            case "player-name":
                self.query_one("#room-name", Input).focus()
            case "room-name":
                self._connect()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "connect-list":
            self._connect()

    def _connect(self) -> None:
        uri = self.query_one("#server-uri", Input).value.strip()
        name = self.query_one("#player-name", Input).value.strip().lower()
        room = self.query_one("#room-name", Input).value.strip() or "default"
        if not uri:
            self.notify("Server is required.", severity="error")
            return
        if not name:
            self.notify("Player name is required.", severity="error")
            return
        self.app.push_screen(MultiplayerGameScreen(uri, name, room))


class MultiplayerGameScreen(Screen):
    CSS_PATH = "../css/game.tcss"
    BINDINGS = [
        Binding("escape", "disconnect", "Disconnect"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, uri: str, name: str, room: str) -> None:
        super().__init__()
        self.uri = uri
        self.player_name = name.lower()
        self.room = room
        self.websocket: Any | None = None
        self.in_lobby = True
        self.latest_state: dict[str, Any] | None = None
        self.latest_lobby: dict[str, Any] | None = None
        self.pending_wild_card: Card | None = None
        self.active = True

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-layout"):
            with Vertical(id="players-panel"):
                yield Label("Players", id="players-title")
                yield Static("", id="players-list", markup=True)
            with Vertical(id="game-panel"):
                yield Static("", id="current-card", markup=True)
                yield RichLog(id="game-log", highlight=True, markup=True, auto_scroll=True)
                yield Static("", id="hand-display", markup=True)
                yield Input(
                    placeholder="/start in lobby, card or blank on your turn",
                    id="card-input",
                    disabled=True,
                )
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{self.player_name}@{self.room}"
        self._log(f"Connecting to {self.uri}...")
        self.run_network_client()

    async def action_disconnect(self) -> None:
        self.active = False
        if self.websocket is not None:
            with contextlib.suppress(Exception):
                await self._send({'action': 'leave'})
                await self.websocket.close()
        self.app.pop_screen()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "card-input":
            return
        text = event.value.strip()
        event.input.clear()
        if self.websocket is None:
            self.notify("Not connected.", severity="warning")
            return
        if self.pending_wild_card is not None:
            await self._send_pending_wild_card(text)
            return
        if self.in_lobby:
            if text in ("", "start", "/start"):
                await self._send({'action': 'start'})
            else:
                self.notify("Type /start when everyone has joined.", severity="warning")
            return
        await self._send_turn_action(text)

    @work(exclusive=True)
    async def run_network_client(self) -> None:
        try:
            import websockets
            from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
        except ImportError:
            self._log("[red]Install the 'websockets' package to use multiplayer.[/red]")
            return

        try:
            async with websockets.connect(self.uri) as websocket:
                self.websocket = websocket
                await self._send({
                    'action': 'join',
                    'name': self.player_name,
                    'room': self.room,
                })
                self.query_one("#card-input", Input).disabled = False
                async for raw_message in websocket:
                    await self._handle_message(raw_message)
                    if not self.active:
                        break
                if self.active:
                    await self._handle_disconnected("Disconnected from server.")
        except InvalidURI:
            await self._handle_disconnected(f"Invalid server address: {self.uri}")
        except InvalidHandshake:
            await self._handle_disconnected("The server rejected the WebSocket connection.")
        except ConnectionClosed as error:
            reason = getattr(error, "reason", "")
            await self._handle_disconnected(f"Disconnected from server{f': {reason}' if reason else '.'}")
        except OSError as error:
            await self._handle_disconnected(f"Could not connect to {self.uri}: {error}")
        finally:
            self.active = False
            self.websocket = None
            with contextlib.suppress(Exception):
                self.query_one("#card-input", Input).disabled = True

    async def _send_turn_action(self, text: str) -> None:
        if self.latest_state is None:
            return
        if not self.latest_state.get('your_turn'):
            self.notify("It is not your turn.", severity="warning")
            return
        if text == '':
            await self._send({'action': 'draw'})
        elif text.upper() == 'PASS' or text == '/pass':
            await self._send({'action': 'pass'})
        else:
            parts = text.upper().split()
            if len(parts) > 1 and parts[0] in ("WILDCARD", "+4"):
                self._log("[red]Select the wild card first, then choose the color when prompted.[/red]")
                return
            card_input = text.upper()
            card = Card.from_str(card_input)
            if card is None:
                self._log('[red]Unknown card. Try "7 GREEN", "+2 BLUE", "WILDCARD", "+4".[/red]')
                return
            if card.is_wild:
                self.pending_wild_card = card
                self.query_one("#card-input", Input).placeholder = "New color (RED / GREEN / BLUE / YELLOW)"
                self._log(f"{card!r} selected. Choose a color.")
                return
            message: dict[str, Any] = {
                'action': 'play',
                'card': card_to_dict(card),
            }
            await self._send(message)

    async def _send_pending_wild_card(self, text: str) -> None:
        if self.pending_wild_card is None:
            return
        try:
            color = CardColor[text.strip().upper()]
        except KeyError:
            self._log("[red]Invalid color. Enter RED, GREEN, BLUE, or YELLOW.[/red]")
            self.query_one("#card-input", Input).placeholder = "New color (RED / GREEN / BLUE / YELLOW)"
            return

        card = self.pending_wild_card
        self.pending_wild_card = None
        self.query_one("#card-input", Input).placeholder = "Waiting..."
        await self._send({
            'action': 'play',
            'card': card_to_dict(card),
            'color': color.name,
        })

    async def _handle_disconnected(self, message: str) -> None:
        self.active = False
        self.pending_wild_card = None
        self._log(f"[red]{message}[/red]")
        self.notify(message, severity="error")
        with contextlib.suppress(Exception):
            input_widget = self.query_one("#card-input", Input)
            input_widget.placeholder = "Disconnected"
            input_widget.disabled = True
        await asyncio.sleep(1.5)
        with contextlib.suppress(Exception):
            self.app.pop_screen()

    async def _handle_message(self, raw_message: str) -> None:
        try:
            message = json.loads(raw_message)
        except json.JSONDecodeError:
            self._log("[red]Server sent invalid JSON.[/red]")
            return

        message_type = message.get('type')
        if message_type == 'lobby':
            self.in_lobby = True
            self.latest_lobby = message
            self._render_lobby(message)
        elif message_type == 'state':
            self.in_lobby = False
            self.latest_state = message['state']
            self._render_state(self.latest_state)
        elif message_type == 'error':
            self._log(f"[red]{message['message']}[/red]")
        elif message_type == 'info':
            self._log(f"[blue]{message['message']}[/blue]")
        elif message_type == 'event':
            self._render_event(message['event'])

    def _render_lobby(self, lobby: dict[str, Any]) -> None:
        players = lobby.get('players', [])
        self.query_one("#players-list", Static).update(
            "\n".join(f"  {player['name']}" for player in players) or "[dim]No players[/dim]"
        )
        rules = lobby.get('rules') or {}
        self.query_one("#current-card", Static).styles.border = ("double", "white")
        self.query_one("#current-card", Static).update(f"Room: {lobby['room']}")
        self.query_one("#hand-display", Static).update(
            f"[dim]Rules:[/dim] {rules.get('starting_cards', 7)} starting cards, "
            f"stacking {'on' if rules.get('card_stacking', True) else 'off'}"
        )
        self.query_one("#card-input", Input).placeholder = "/start"

    def _render_state(self, state: dict[str, Any]) -> None:
        lines = []
        for player in state['players']:
            is_current = player['name'] == state['turn']
            prefix = "[bold]> " if is_current else "  "
            suffix = f" ({player['cards']})[/bold]" if is_current else f" ({player['cards']})"
            lines.append(f"{prefix}{player['name']}{suffix}")
        self.query_one("#players-list", Static).update("\n".join(lines))

        card = card_from_dict(state['top_card'])
        color_name = card.color.name.lower() if card.color else "white"
        current_card = self.query_one("#current-card", Static)
        current_card.styles.border = ("double", color_name)
        current_card.update(Text.from_markup(f"[bright_{color_name}]  {card!r}  [/bright_{color_name}]"))

        prompt = "Your turn: card, blank to draw, PASS to skip" if state['your_turn'] else "Waiting..."
        self.query_one("#hand-display", Static).update(hand_text(state['you']['hand']))
        self.query_one("#card-input", Input).placeholder = prompt
        if state.get('winner') is not None:
            self._log(f"[green]Winner: {state['winner']}[/green]")
            self.active = False
        elif not state.get('active', True):
            self._log("[yellow]Game ended.[/yellow]")
            self.active = False

    def _render_event(self, event: dict[str, Any]) -> None:
        if event['type'] == 'STACKING_ACTIVE':
            for card in event['payload'].get('stacked_cards', []):
                self._log(f"[dim]Stacked: {card_from_dict(card)}[/dim]")
        elif event['type'] == 'COLOR_CHANGED':
            self._log(
                f"{event['payload'].get('player')} changed color to "
                f"{event['payload'].get('new_color')}."
            )

    async def _send(self, message: dict[str, Any]) -> None:
        if self.websocket is None:
            return
        try:
            await self.websocket.send(json.dumps(message))
        except Exception as error:
            if error.__class__.__name__.startswith("ConnectionClosed") or isinstance(error, OSError):
                await self._handle_disconnected("Disconnected from server.")
                return
            raise

    def _log(self, message: str) -> None:
        self.query_one("#game-log", RichLog).write(message)
