import sys
import argparse
import logging

from textual.app import App

from uno._version import __VERSION__
from uno.screens.menu import MainMenuScreen


class UNOApp(App):
    TITLE = "UNO"

    def __init__(self, cheats: bool = False) -> None:
        super().__init__()
        self.cheats = cheats

    def on_mount(self) -> None:
        self.push_screen(MainMenuScreen())


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
