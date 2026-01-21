from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live


SUIT_SYMBOLS = {
    "hearts": "♥",
    "diamonds": "♦",
    "clubs": "♣",
    "spades": "♠",
    "♥": "♥",
    "♦": "♦",
    "♣": "♣",
    "♠": "♠",
    "H": "♥",
    "D": "♦",
    "C": "♣",
    "S": "♠",
}

SUIT_COLORS = {
    "♥": "red",
    "♦": "red",
    "♣": "cyan",
    "♠": "cyan",
}

STATUS_STYLES = {
    "WINNER": "bold green",
    "NATURAL BLACKJACK": "bold green",
    "BUSTED": "bold red",
    "STAY": "yellow",
    "CURRENT TURN": "bold blink blue",
}


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str


class BlackjackUI:
    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()
        self.layout = Layout(name="root")
        self.layout.split_column(
            Layout(name="dealer", size=9),
            Layout(name="seats", ratio=3),
            Layout(name="log", size=8),
        )
        self.live = Live(self.layout, console=self.console, refresh_per_second=8, screen=True)
        self._started = False

    def start(self) -> None:
        if not self._started:
            self.live.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self.live.stop()
            self._started = False

    def update_table(self, game_state: dict) -> None:
        self.start()
        dealer_panel = self._build_dealer_panel(game_state.get("dealer", {}))
        seats_panel = self._build_seats_panel(game_state.get("players", []))
        log_panel = self._build_log_panel(game_state.get("event_log", []))

        self.layout["dealer"].update(dealer_panel)
        self.layout["seats"].update(seats_panel)
        self.layout["log"].update(log_panel)
        self.live.refresh()

    def _build_dealer_panel(self, dealer_state: dict) -> Panel:
        dealer_cards = dealer_state.get("cards", [])
        hidden_cards = dealer_state.get("hidden_cards", 0)
        card_renders = [self._render_card(card) for card in dealer_cards]
        for _ in range(hidden_cards):
            card_renders.append(self._render_card_back())
        cards = Align.center(Columns(card_renders, padding=1), vertical="middle")
        title = Text("DEALER", style="bold white")
        return Panel(cards, title=title, border_style="bold magenta")

    def _build_seats_panel(self, players: Iterable[Optional[dict]]) -> Panel:
        table = Table.grid(expand=True)
        for _ in range(5):
            table.add_column(ratio=1)

        player_panels = []
        players_list = list(players)
        while len(players_list) < 5:
            players_list.append(None)

        for player_state in players_list[:5]:
            player_panels.append(self._build_player_panel(player_state))

        table.add_row(*player_panels)
        return Panel(table, title="Players", border_style="bright_black")

    def _build_player_panel(self, player_state: Optional[dict]) -> Panel:
        if not player_state:
            vacant = Align.center(Text("[ VACANT ]", style="dim"), vertical="middle")
            return Panel(vacant, border_style="dim")

        name = player_state.get("name", "Player")
        is_local = player_state.get("is_local", False)
        if is_local:
            name = f"{name} (YOU)"
        score = player_state.get("score", "-")
        status = player_state.get("status", "")
        is_current = player_state.get("is_current", False)
        if is_current:
            status = "CURRENT TURN"

        status_text = Text(status)
        if status in STATUS_STYLES:
            status_text.stylize(STATUS_STYLES[status])

        cards = player_state.get("cards", [])
        card_group = Columns([self._render_card(card) for card in cards], padding=1)
        info = Table.grid(padding=(0, 1))
        info.add_row(Text(name, style="bold white"))
        info.add_row(Text(f"Score: {score}", style="white"))
        if status:
            info.add_row(status_text)
        body = Group(info, Align.center(card_group))
        border_style = "bright_blue" if is_current else "white"
        return Panel(body, border_style=border_style)

    def _build_log_panel(self, log_entries: Iterable[str]) -> Panel:
        log_lines = list(log_entries)[-4:]
        if not log_lines:
            log_lines = ["Waiting for actions..."]
        log_table = Table.grid(padding=0)
        for entry in log_lines:
            log_table.add_row(Text(f"• {entry}", style="white"))
        return Panel(log_table, title="Game Activity", border_style="bright_black")

    def _render_card(self, card: object) -> Text:
        normalized = self._normalize_card(card)
        suit_symbol = SUIT_SYMBOLS.get(normalized.suit, normalized.suit)
        color = SUIT_COLORS.get(suit_symbol, "white")
        rank = normalized.rank
        markup = (
            "┌───────┐\n"
            f"│ [{color}]{rank:<5}[/{color}] │\n"
            f"│   [{color}]{suit_symbol}[/{color}]   │\n"
            f"│ [{color}]{rank:>5}[/{color}] │\n"
            "└───────┘"
        )
        return Text.from_markup(markup)

    def _render_card_back(self) -> Text:
        markup = (
            "┌───────┐\n"
            "│[bold blue]░░░░░░░[/bold blue]│\n"
            "│[bold blue]░░░░░░░[/bold blue]│\n"
            "│[bold blue]░░░░░░░[/bold blue]│\n"
            "└───────┘"
        )
        return Text.from_markup(markup)

    def _normalize_card(self, card: object) -> Card:
        if isinstance(card, Card):
            return card
        if isinstance(card, dict):
            rank = str(card.get("rank", "?"))
            suit = str(card.get("suit", "?"))
            return Card(rank=rank, suit=suit)
        if isinstance(card, (list, tuple)) and len(card) >= 2:
            rank = str(card[0])
            suit = str(card[1])
            return Card(rank=rank, suit=suit)
        if isinstance(card, str):
            stripped = card.strip()
            if len(stripped) >= 2:
                rank = stripped[:-1]
                suit = stripped[-1]
                return Card(rank=rank, suit=suit)
        return Card(rank="?", suit="?")
