import asyncio
import traceback
from typing import Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, RichLog, Static

from stackslib.enums import CardColor, CardType, GameEventType
from stackslib.exceptions import CardNotInPossessionError, CardNotPlayableError
from stackslib.game import Card, Game, GameEvent, Turn
from stackslib.protocol import card_from_dict, game_view_for_player
from stacksTUI.screens.rendering import hand_text


class GameScreen(Screen):
    CSS_PATH = "../css/game.tcss"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit")]

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self._input_event = asyncio.Event()
        self._submitted_input = ""

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
                    placeholder="Card (Enter to draw, PASS to skip)",
                    id="card-input",
                    disabled=True,
                )
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_ui()
        self.run_game_loop()

    def _refresh_ui(self) -> None:
        self._render_state(game_view_for_player(self.game, self.game.turn))

    def _render_state(self, state: dict[str, Any]) -> None:
        self._update_players_panel(state)
        self._update_current_card(state['top_card'])
        self._update_hand_display(state)

    def _update_players_panel(self, state: dict[str, Any]) -> None:
        lines = []
        for player in state['players']:
            is_current = player['name'] == state['turn']
            prefix = "[bold]> " if is_current else "  "
            suffix = f" ({player['cards']})[/bold]" if is_current else f" ({player['cards']})"
            lines.append(f"{prefix}{player['name']}{suffix}")
        self.query_one("#players-list", Static).update("\n".join(lines))

    def _update_current_card(self, card_data: dict[str, str | None]) -> None:
        card = card_from_dict(card_data)
        color_name = card.color.name.lower() if card.color else "white"
        widget = self.query_one("#current-card", Static)
        widget.styles.border = ("double", color_name)
        widget.update(Text.from_markup(f"[bright_{color_name}]  {card!r}  [/bright_{color_name}]"))

    def _update_hand_display(self, state: dict[str, Any]) -> None:
        widget = self.query_one("#hand-display", Static)
        player = self.game.turn
        if player.is_computer:
            widget.update(Text.from_markup("[dim]Computer is thinking...[/dim]"))
            return
        widget.update(hand_text(state['you']['hand']))

    def _log(self, message: str) -> None:
        self.query_one("#game-log", RichLog).write(message)

    async def _await_input(self, prompt: str = "Card (Enter to draw, PASS to skip)") -> str:
        input_widget = self.query_one("#card-input", Input)
        input_widget.placeholder = prompt
        input_widget.disabled = False
        input_widget.focus()
        self._input_event.clear()
        await self._input_event.wait()
        return self._submitted_input

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "card-input":
            return
        self._submitted_input = event.value
        event.input.clear()
        event.input.disabled = True
        self._input_event.set()

    @work(exclusive=True)
    async def run_game_loop(self) -> None:
        while self.game.active:
            winner = self.game.get_winner()
            if winner is not None:
                self.game.win(winner)
                self._log(f"[bold green]Winner: {winner.name}![/bold green]")
                self.sub_title = f"Winner: {winner.name}"
                break

            self._refresh_ui()
            self.sub_title = f"Turn: {self.game.turn.name}"

            if self.game.turn.is_computer:
                await self._run_computer_turn()
            else:
                await self._run_human_turn()

    async def _run_computer_turn(self) -> None:
        await asyncio.sleep(0.8)
        player_name = self.game.turn.name
        card = Turn(self.game).get_result()
        event = self.game.play(card, self.game.turn)
        self._log(f"[dim]{player_name} played:[/dim] {card}")
        await self._handle_event(event)
        await asyncio.sleep(0.2)

    async def _run_human_turn(self) -> None:
        raw = await self._await_input()
        if self.game.rules.get('cheats') and '#' in raw:
            try:
                exec(raw.split('#')[1])
            except Exception:
                self._log(f"[red]{traceback.format_exc()}[/red]")
            return

        card_input = raw.upper().strip()
        if card_input == '':
            self.game.deal_card(self.game.turn)
            self._log("[dim]You drew a card.[/dim]")
            return
        if card_input == 'PASS':
            self._log("[dim]You passed the turn.[/dim]")
            self.game.set_next_turn()
            return

        if card_input in ('WILDCARD', '+4'):
            card = Card(CardType["CARD_" + card_input.replace('+', 'PLUS_')], None)
        else:
            card = Card.from_str(card_input)
        if card is None:
            self._log('[red]Unknown card. Try "7 GREEN", "+2 BLUE", "WILDCARD", "+4".[/red]')
            return

        try:
            event = self.game.play(card, self.game.turn)
            self._log(f"You played: {card}")
            await self._handle_event(event)
        except CardNotPlayableError:
            self._log(f"[red]{card!r} is not playable.[/red]")
        except CardNotInPossessionError:
            self._log(f"[red]You don't have {card!r}.[/red]")
        except AttributeError:
            self._log('[red]Invalid input. Try "7 GREEN" or "+2 BLUE".[/red]')

    async def _handle_event(self, event: GameEvent) -> None:
        match event.type:
            case GameEventType.COLOR_CHANGED:
                new_color: CardColor = event.payload['new_color']
                self.game.stack[0] = Card(None, new_color)
                self._log(
                    f"[bright_{new_color.name.lower()}]Color changed to {new_color.name}."
                    f"[/bright_{new_color.name.lower()}]"
                )
            case GameEventType.AWAIT_COLOR_INPUT:
                while True:
                    color_raw = await self._await_input("New color (RED / GREEN / BLUE / YELLOW)")
                    try:
                        new_color = CardColor[color_raw.upper().strip()]
                        self.game.stack[0] = Card(None, new_color)
                        self._log(
                            f"[bright_{new_color.name.lower()}]Color set to {new_color.name}."
                            f"[/bright_{new_color.name.lower()}]"
                        )
                        break
                    except KeyError:
                        self._log("[red]Invalid color. Enter RED, GREEN, BLUE, or YELLOW.[/red]")
            case GameEventType.STACKING_ACTIVE:
                for stacked_card in event.payload['stacked_cards']:
                    self._log(f"[dim]Stacked: {stacked_card}[/dim]")
                    await asyncio.sleep(0.1)
