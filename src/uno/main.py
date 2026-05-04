import sys
import asyncio
import argparse
import traceback

from uno.game import *

from rich.text import Text

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input, Button, Static, RichLog, Label, Checkbox, Rule
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.binding import Binding
from textual import work

__VERSION__: str = 'ALPHA-2026-05-04'

_LOGO = (
    "[red]88   88[/red][green] 88b 88[/green][blue]  dP\"Yb  [/blue]\n"
    "[red]88   88[/red][green] 88Yb88[/green][blue] dP   Yb [/blue]\n"
    "[red]Y8   8P[/red][green] 88 Y88[/green][blue] Yb   dP [/blue]\n"
    "[red]`YbodP'[/red][green] 88  Y8[/green][blue]  YbodP  [/blue]"
)


class SetupScreen(Screen):
    CSS_PATH = "css/setup.tcss"

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="setup-container"):
            yield Static(_LOGO, markup=True, id="logo")
            yield Label(f"version {__VERSION__}", classes="hint")
            yield Rule()
            yield Label("Number of players:", classes="field-label")
            yield Input(value="2", id="num-players")
            yield Rule()
            yield Label("Player names:", classes="field-label")
            yield Label('type "computer" for AI', classes="hint")
            with Vertical(id="player-names"):
                yield Input(placeholder="Player #1", id="player-1")
                yield Input(placeholder="Player #2", id="player-2")
            yield Rule()
            yield Label("Starting cards:", classes="field-label")
            yield Input(value="7", id="starting-cards")
            yield Rule()
            yield Checkbox("Similar card stacking", value=True, id="card-stacking")
            yield Button("Start Game", id="start-button")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "num-players":
            return
        try:
            count = int(event.value)
            if count >= 2:
                self._sync_player_inputs(count)
        except ValueError:
            pass

    def _sync_player_inputs(self, count: int) -> None:
        container = self.query_one("#player-names", Vertical)
        existing = list(container.query(Input))
        current = len(existing)
        if count > current:
            for i in range(current + 1, count + 1):
                container.mount(Input(placeholder=f"Player #{i}", id=f"player-{i}"))
        elif count < current:
            for widget in existing[count:]:
                widget.remove()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-button":
            self._try_start()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "start-button":
            self._try_start()

    def _try_start(self) -> None:
        try:
            num_players = int(self.query_one("#num-players", Input).value)
            if num_players < 2:
                self.notify("Need at least 2 players.", severity="error")
                return
        except ValueError:
            self.notify("Enter a valid number of players.", severity="error")
            return

        players: list[Player] = []
        seen: set[str] = set()
        for i in range(1, num_players + 1):
            name = self.query_one(f"#player-{i}", Input).value.strip().lower()
            if not name:
                self.notify(f"Player #{i} needs a name.", severity="error")
                return
            if name in seen:
                self.notify(f"Duplicate name: {name}", severity="error")
                return
            seen.add(name)
            players.append(Player(name))

        try:
            starting_cards = int(self.query_one("#starting-cards", Input).value)
            if starting_cards < 2:
                self.notify("Starting cards must be at least 2.", severity="error") # FIXME: Grammar
                return
        except ValueError:
            self.notify("Enter a valid number for starting cards.", severity="error")
            return

        card_stacking = self.query_one("#card-stacking", Checkbox).value

        rules: dict = {
            'starting_cards': starting_cards,
            'cheats': self.app.cheats,
            'card_stacking': card_stacking,
        }
        game = Game(players, rules)
        self.app.push_screen(GameScreen(game))


class GameScreen(Screen):
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
    ]

    CSS_PATH = "css/game.tcss"

    def __init__(self, game: Game) -> None:
        super().__init__()
        self.game = game
        self._input_event: asyncio.Event = asyncio.Event()
        self._submitted_input: str = ""

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
        self._update_players_panel()
        self._update_current_card()
        self._update_hand_display()

    def _update_players_panel(self) -> None:
        lines = []
        for player in self.game.players:
            is_current = player == self.game.turn
            prefix = "[bold]> " if is_current else "  "
            suffix = f" ({len(player.hand)})[/bold]" if is_current else f" ({len(player.hand)})"
            lines.append(f"{prefix}{player.name}{suffix}")
        self.query_one("#players-list", Static).update("\n".join(lines))

    def _update_current_card(self) -> None:
        card = self.game.last_played_card
        color_name = card.color.name.lower() if card.color else "white"
        widget = self.query_one("#current-card", Static)
        widget.styles.border = ("double", color_name)
        widget.update(Text.from_markup(f"[bright_{color_name}]  {card!r}  [/bright_{color_name}]"))

    def _update_hand_display(self) -> None:
        player = self.game.turn
        widget = self.query_one("#hand-display", Static)
        if not player.is_computer:
            label = Text.from_markup("[dim]Your hand:[/dim] ")
            label.append_text(Text.from_markup(player.format_hand_contents()))
            widget.update(label)
        else:
            widget.update(Text.from_markup("[dim]Computer is thinking...[/dim]"))

    def _log(self, message: str) -> None:
        self.query_one("#game-log", RichLog).write(message)

    async def _await_input(self, prompt: str = "Card (Enter to draw, PASS to skip)") -> str:
        inp = self.query_one("#card-input", Input)
        inp.placeholder = prompt
        inp.disabled = False
        inp.focus()
        self._input_event.clear()
        await self._input_event.wait()
        return self._submitted_input

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "card-input":
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
                await asyncio.sleep(0.8)
                player_name = self.game.turn.name
                computer_turn = Turn(self.game)
                card = computer_turn.get_result()
                event = self.game.play(card, self.game.turn)
                self._log(f"[dim]{player_name} played:[/dim] {card}")
                await self._handle_event(event, is_computer=True)
                self._update_players_panel()
                await asyncio.sleep(0.2)
            else:
                raw = await self._await_input()

                if self.game.rules.get('cheats') and '#' in raw:
                    try:
                        exec(raw.split('#')[1])
                    except Exception:
                        self._log(f"[red]{traceback.format_exc()}[/red]")
                    continue

                card_input = raw.upper().strip()

                if card_input == '':
                    self.game.deal_card(self.game.turn)
                    self._log("[dim]You drew a card.[/dim]")
                elif card_input == 'PASS':
                    self._log("[dim]You passed the turn.[/dim]")
                    self.game.set_next_turn()
                else:
                    if card_input in ('WILDCARD', '+4'):
                        card = Card(CardType["CARD_" + card_input.replace('+', 'PLUS_')], None)
                    else:
                        card = Card.from_str(card_input)

                    if card is None:
                        self._log('[red]Unknown card. Try "7 GREEN", "+2 BLUE", "WILDCARD", "+4".[/red]')
                        continue

                    try:
                        event = self.game.play(card, self.game.turn)
                        self._log(f"You played: {card}")
                        await self._handle_event(event, is_computer=False)
                        self._update_players_panel()
                    except CardNotPlayableError:
                        self._log(f"[red]{card!r} is not playable.[/red]")
                        continue
                    except CardNotInPossessionError:
                        self._log(f"[red]You don't have {card!r}.[/red]")
                        continue
                    except AttributeError:
                        self._log('[red]Invalid input. Try "7 GREEN" or "+2 BLUE".[/red]')
                        continue

    async def _handle_event(self, event: GameEvent, is_computer: bool) -> None:
        match event.type:
            case GameEventType.COLOR_CHANGED:
                new_color: CardColor = event.payload['new_color']
                self.game.stack[0] = Card(None, new_color)
                self._log(
                    f"[bright_{new_color.name.lower()}]Color changed to {new_color.name}.[/bright_{new_color.name.lower()}]"
                )
                self._update_current_card()
            case GameEventType.AWAIT_COLOR_INPUT:
                while True:
                    color_raw = await self._await_input("New color (RED / GREEN / BLUE / YELLOW)")
                    try:
                        new_color = CardColor[color_raw.upper().strip()]
                        self.game.stack[0] = Card(None, new_color)
                        self._log(
                            f"[bright_{new_color.name.lower()}]Color set to {new_color.name}.[/bright_{new_color.name.lower()}]"
                        )
                        self._update_current_card()
                        break
                    except KeyError:
                        self._log("[red]Invalid color. Enter RED, GREEN, BLUE, or YELLOW.[/red]")
            case GameEventType.STACKING_ACTIVE:
                for stacked_card in event.payload['stacked_cards']:
                    self._log(f"[dim]Stacked: {stacked_card}[/dim]")
                    await asyncio.sleep(0.1)


class UNOApp(App):
    TITLE = "UNO"
    THEME = "ansi-dark"

    def __init__(self, cheats: bool = False) -> None:
        super().__init__()
        self.cheats = cheats

    def on_mount(self) -> None:
        self.push_screen(SetupScreen())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('-C', '--cheats', action='store_true', help="enable cheat codes")
    parser.add_argument('-D', '--debug', action='store_true', help="enable debug logging")
    parser.add_argument('-V', '--version', action='store_true', help="print version and exit")
    args = parser.parse_args()

    if args.version:
        print(f"UNO | version {__VERSION__}")
        sys.exit(0)

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(levelname)s: %(message)s',
    )

    UNOApp(cheats=args.cheats).run()
