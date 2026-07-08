from rich.text import Text

from stackslib.game import Card
from stackslib.protocol import card_from_dict


def card_text(card: Card) -> Text:
    color_name = card.color.name.lower() if card.color else "white"
    return Text(repr(card), style=f"bright_{color_name}")


def hand_text(cards: list[dict[str, str | None]]) -> Text:
    text = Text.from_markup("[dim]Your hand:[/dim] ")
    for index, card_data in enumerate(cards):
        if index:
            text.append(", ")
        text.append_text(card_text(card_from_dict(card_data)))
    return text
