from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from stacksTUI._version import __VERSION__, _LOGO


class AboutScreen(Screen):
    CSS_PATH = "../css/about.tcss"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="about-layout"):
            yield Static(_LOGO, markup=True, id="logo")
            yield Static(
                f"[bold]stacksTUI[/bold] | version {__VERSION__}\n\n"
                "A Textual interface for the stackslib card game engine.\n\n"
                "[dim]Press Escape to go back.[/dim]",
                markup=True,
                id="about-text",
            )
        yield Footer()
