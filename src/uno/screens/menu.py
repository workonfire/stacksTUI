from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, OptionList, Static

from uno._version import __VERSION__, _LOGO


class MainMenuScreen(Screen):
    CSS_PATH = "../css/menu.tcss"
    BINDINGS = [Binding("q", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="menu-layout"):
            yield Static(_LOGO, markup=True, id="logo")
            yield Label(f"version {__VERSION__}", id="version-label")
            yield OptionList(
                "> Singleplayer",
                "> Multiplayer",
                "> Options",
                "> About",
                id="main-menu",
            )
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        from uno.screens.about import AboutScreen
        from uno.screens.multiplayer import MultiplayerSetupScreen
        from uno.screens.setup import SetupScreen

        match event.option_index:
            case 0:
                self.app.push_screen(SetupScreen())
            case 1:
                self.app.push_screen(MultiplayerSetupScreen())
            case 2:
                self.notify("Options not yet implemented.", severity="warning")
            case 3:
                self.app.push_screen(AboutScreen())
