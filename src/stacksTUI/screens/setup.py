from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Label, OptionList, Static

from stacksTUI._version import _LOGO
from stackslib.game import Game, Player


class SetupScreen(Screen):
    CSS_PATH = "../css/setup.tcss"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def __init__(self) -> None:
        super().__init__()
        self._card_stacking = True

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="setup-outer"):
            with VerticalScroll(id="setup-layout"):
                yield Static(_LOGO, markup=True, id="logo")
                yield Label("--- new local game ---", id="setup-title")
                with Horizontal(id="settings-row"):
                    with Vertical(classes="field-group"):
                        yield Label("players", classes="option-label")
                        yield Input(value="2", id="num-players")
                    with Vertical(classes="field-group"):
                        yield Label("starting cards", classes="option-label")
                        yield Input(value="7", id="starting-cards")
                    with Vertical(classes="field-group"):
                        yield Label("stacking", classes="option-label")
                        yield OptionList("yes", "no", id="stacking-list")
                yield Label("player names", classes="option-label")
                with Horizontal(id="player-names"):
                    yield Input(placeholder="player 1", id="player-1")
                    yield Input(placeholder="player 2", id="player-2")
                yield OptionList("start", id="start-list")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#num-players", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "num-players":
            return
        try:
            count = int(event.value)
            if 2 <= count <= 10:
                self._sync_player_inputs(count)
        except ValueError:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_id = event.input.id
        if input_id == "num-players":
            self.query_one("#player-1", Input).focus()
        elif input_id == "starting-cards":
            self.query_one("#stacking-list", OptionList).focus()
        elif input_id and input_id.startswith("player-"):
            n = int(input_id.split("-")[1])
            try:
                self.query_one(f"#player-{n + 1}", Input).focus()
            except Exception:
                self.query_one("#starting-cards", Input).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        match event.option_list.id:
            case "stacking-list":
                self._card_stacking = event.option_index == 0
                self.query_one("#start-list", OptionList).focus()
            case "start-list":
                self._try_start()

    def _sync_player_inputs(self, count: int) -> None:
        container = self.query_one("#player-names", Horizontal)
        existing = list(container.query(Input))
        current = len(existing)
        if count > current:
            for i in range(current + 1, count + 1):
                container.mount(Input(placeholder=f"player {i}", id=f"player-{i}"))
        elif count < current:
            for widget in existing[count:]:
                widget.remove()

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
                self.notify(f"Player {i} needs a name.", severity="error")
                return
            if name in seen:
                self.notify(f"Duplicate name: {name}", severity="error")
                return
            seen.add(name)
            players.append(Player(name))

        try:
            starting_cards = int(self.query_one("#starting-cards", Input).value)
            if starting_cards < 2:
                self.notify("Starting cards must be at least 2.", severity="error")
                return
        except ValueError:
            self.notify("Enter a valid number for starting cards.", severity="error")
            return

        rules = {
            'starting_cards': starting_cards,
            'cheats': self.app.cheats,
            'card_stacking': self._card_stacking,
        }
        from stacksTUI.screens.game import GameScreen

        self.app.push_screen(GameScreen(Game(players, rules)))
