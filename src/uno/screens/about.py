from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Static
from textual.containers import Vertical
from textual.binding import Binding

from uno._version import __VERSION__, _LOGO


class AboutScreen(Screen):
    CSS_PATH = "../css/about.tcss"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="about-layout"):
            yield Static(_LOGO, markup=True, id="logo")
            yield Static(
                f"[bold]UNO[/bold] — version {__VERSION__}\n\n"
                "A terminal implementation of the UNO card game.\n\n"
                "[dim]Press Escape to go back.[/dim]",
                markup=True,
                id="about-text",
            )
        yield Footer()
