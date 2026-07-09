import argparse
import asyncio
import logging
import sys

from stacksTUI._version import __VERSION__

try:
    from textual.app import App
    TEXTUAL_IMPORT_ERROR: ModuleNotFoundError | None = None
except ModuleNotFoundError as error:
    App = object  # type: ignore[assignment,misc]
    TEXTUAL_IMPORT_ERROR = error


class StacksTUIApp(App):
    TITLE = "stacksTUI"
    ALLOWED_THEMES = ("ansi-dark", "ansi-light")

    def __init__(
        self,
        cheats: bool = False,
        connect_uri: str | None = None,
        player_name: str | None = None,
        room: str = "main",
    ) -> None:
        super().__init__()
        for theme_name in list(self.available_themes):
            if theme_name not in self.ALLOWED_THEMES:
                self.unregister_theme(theme_name)
        self.theme = "ansi-dark"
        self.cheats = cheats
        self.connect_uri = connect_uri
        self.player_name = player_name
        self.room = room

    def on_mount(self) -> None:
        if self.connect_uri is not None and self.player_name is not None:
            from stacksTUI.screens.multiplayer import MultiplayerGameScreen

            self.push_screen(MultiplayerGameScreen(self.connect_uri, self.player_name, self.room))
            return

        from stacksTUI.screens.menu import MainMenuScreen

        self.push_screen(MainMenuScreen())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('-C', '--cheats', action='store_true', help="enable cheat codes")
    parser.add_argument('-D', '--debug', action='store_true', help="enable debug logging")
    parser.add_argument('-V', '--version', action='store_true', help="print version and exit")
    parser.add_argument('--serve', action='store_true', help="host an internet/LAN multiplayer server")
    parser.add_argument('--host', default='127.0.0.1', help="host interface for --serve")
    parser.add_argument('--port', type=int, default=8765, help="port for --serve")
    parser.add_argument('--starting-cards', type=int, default=7, help="starting cards for --serve")
    parser.add_argument('--disable-card-stacking', action='store_true', help="disable card stacking for --serve")
    parser.add_argument('--connect', help="connect to a multiplayer server, for example ws://127.0.0.1:8765")
    parser.add_argument('--name', help="player name for multiplayer")
    parser.add_argument('--room', default='main', help="multiplayer room name")
    args = parser.parse_args()

    if args.version:
        print(f"stacksTUI | version {__VERSION__}")
        raise SystemExit

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(levelname)s: %(message)s',
    )

    if args.serve:
        from stackslib.server import serve

        if args.starting_cards <= 1:
            raise SystemExit("Starting cards can't be lower than 2.")
        asyncio.run(serve(
            args.host,
            args.port,
            {
                'starting_cards': args.starting_cards,
                'card_stacking': not args.disable_card_stacking,
            },
        ))
        return

    if args.connect and not args.name:
        raise SystemExit("--name is required with --connect")

    if TEXTUAL_IMPORT_ERROR is not None:
        raise SystemExit("Install the 'textual' package to run stacksTUI.") from TEXTUAL_IMPORT_ERROR

    StacksTUIApp(
        cheats=args.cheats,
        connect_uri=args.connect,
        player_name=args.name,
        room=args.room,
    ).run()
