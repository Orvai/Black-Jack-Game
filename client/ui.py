from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Optional

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.progress import ProgressBar
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

SHUFFLE_FRAMES = [
    """
    ┌───────┐         ┌───────┐
    │ A♠    │  ⇢⇢⇢    │    9♦ │
    │   ♠   │         │   ♦   │
    │    A♠ │    ⇠⇠⇠  │ 9♦    │
    └───────┘         └───────┘
    """,
    """
    ┌───────┐    ⇢⇢⇢  ┌───────┐
    │ K♣    │         │    7♥ │
    │   ♣   │   ⇢⇢⇢   │   ♥   │
    │    K♣ │         │ 7♥    │
    └───────┘  ⇠⇠⇠    └───────┘
    """,
    """
    ┌───────┐         ┌───────┐
    │ Q♦    │   ⇢⇢⇢   │    J♠ │
    │   ♦   │   ⇠⇠⇠   │   ♠   │
    │    Q♦ │         │ J♠    │
    └───────┘         └───────┘
    """,
]


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
            Layout(name="opponents", ratio=2),
            Layout(name="player", size=16),
        )
        self.live = Live(self.layout, console=self.console, refresh_per_second=8, screen=True)
        self._started = False
        self._turn_started_at: Optional[float] = None
        self._turn_player_key: Optional[str] = None

    def start(self) -> None:
        if not self._started:
            self.live.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self.live.stop()
            self._started = False

    def update_table(self, game_state: dict, player_map: Optional[dict] = None) -> None:
        self.start()
        dealer_panel = self._build_dealer_panel(game_state.get("dealer", {}))
        seats = self._map_player_seats(game_state.get("players", []), player_map)
        local_player = seats.get(1)
        opponents_panel = self._build_opponents_panel([seats.get(i) for i in range(2, 6)])
        player_panel = self._build_player_dashboard(local_player, game_state.get("event_log", []))

        self.layout["dealer"].update(dealer_panel)
        self.layout["opponents"].update(opponents_panel)
        self.layout["player"].update(player_panel)
        self.live.refresh()

    def render_shuffling(self, frame_index: int = 0) -> Panel:
        frame = SHUFFLE_FRAMES[frame_index % len(SHUFFLE_FRAMES)]
        animation = Align.center(Text(frame.strip("\n"), style="bold cyan"), vertical="middle")
        return Panel(animation, title="Shuffling", border_style="bold magenta")

    def get_action_prompt(self) -> str:
        was_started = self._started
        if was_started:
            self.stop()
        self.console.print("\x1b[2K\r", end="")
        choice = self.console.input(
            "[bold yellow]Select Action: [H] Hit | [S] Stand | [Q] Quit[/] "
        )
        if was_started:
            self.start()
        return choice.strip().lower()

    def _map_player_seats(self, players: Iterable[Optional[dict]], player_map: Optional[dict]) -> dict:
        seats: dict[int, Optional[dict]] = {i: None for i in range(1, 6)}
        if isinstance(players, dict):
            iterable = list(players.items())
        else:
            iterable = []
            for idx, player in enumerate(players):
                if not player:
                    continue
                player_id = player.get("id", player.get("player_id", idx + 1))
                iterable.append((player_id, player))

        for player_id, player in iterable:
            seat_index = None
            if player_map and player_id in player_map:
                seat_index = int(player_map[player_id])
            if not seat_index:
                seat_index = int(player.get("seat", 0)) if player else 0
            if not seat_index and player and player.get("is_local"):
                seat_index = 1
            if not seat_index:
                for candidate in range(2, 6):
                    if seats[candidate] is None:
                        seat_index = candidate
                        break
            if seat_index in seats:
                seats[seat_index] = player

        return seats

    def _build_dealer_panel(self, dealer_state: dict) -> Panel:
        dealer_cards = dealer_state.get("cards", [])
        hidden_cards = dealer_state.get("hidden_cards", 0)
        card_renders = [self._render_card(card) for card in dealer_cards]
        for _ in range(hidden_cards):
            card_renders.append(self._render_card_back())
        cards = Align.center(Columns(card_renders, padding=1), vertical="middle")
        title = Text("DEALER", style="bold white")
        return Panel(cards, title=title, border_style="bold magenta")

    def _build_opponents_panel(self, opponents: Iterable[Optional[dict]]) -> Panel:
        table = Table.grid(expand=True)
        for _ in range(4):
            table.add_column(ratio=1)
        opponent_panels = [self._build_opponent_panel(player_state) for player_state in opponents]
        table.add_row(*opponent_panels)
        return Panel(table, title="Opponents", border_style="bright_black")

    def _build_opponent_panel(self, player_state: Optional[dict]) -> Panel:
        if not player_state:
            vacant = Align.center(Text("[ VACANT ]", style="dim"), vertical="middle")
            return Panel(vacant, border_style="dim")

        name = player_state.get("name", "Player")
        score = player_state.get("score", "-")
        status = player_state.get("status", "")
        is_current = player_state.get("is_current", False)
        player_key = str(player_state.get("id", player_state.get("player_id", name)))
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

        renderables: list = [info, Align.center(card_group)]
        if is_current:
            renderables.append(self._build_turn_timer(player_key))

        if self._is_winner(player_state):
            renderables.append(self._render_confetti())

        body = Group(*renderables)
        border_style = "bold blink green" if is_current else "white"
        return Panel(body, border_style=border_style)

    def _build_player_dashboard(self, player_state: Optional[dict], log_entries: Iterable[str]) -> Panel:
        if not player_state:
            waiting = Align.center(Text("Waiting for seat...", style="dim"), vertical="middle")
            return Panel(waiting, title="Player Dashboard", border_style="bright_black")

        name = player_state.get("name", "Player")
        score = player_state.get("score", "-")
        bankroll = player_state.get("bankroll", "-")
        status = player_state.get("status", "")
        is_current = player_state.get("is_current", False)
        status_text = Text(status)
        if status in STATUS_STYLES:
            status_text.stylize(STATUS_STYLES[status])

        header = Table.grid(expand=True)
        header.add_column(ratio=2)
        header.add_column(ratio=1, justify="right")
        header.add_row(Text(f"{name} (YOU)", style="bold white"), Text(f"Bankroll: {bankroll}", style="bold yellow"))
        header.add_row(Text(f"Score: {score}", style="white"), status_text if status else Text(""))

        cards = player_state.get("cards", [])
        card_group = Columns([self._render_card_large(card) for card in cards], padding=2)
        cards_panel = Panel(Align.center(card_group), title="Your Hand", border_style="bright_blue")

        log_panel = self._build_log_panel(log_entries)
        left_column = Layout(name="player_left")
        left_column.split_column(
            Layout(cards_panel, ratio=3),
            Layout(log_panel, ratio=1),
        )

        action_panel = self._render_action_buttons(is_current)
        right_column = Layout(name="player_right")
        right_column.update(action_panel)

        body = Layout()
        body.split_row(
            Layout(left_column, ratio=3),
            Layout(right_column, ratio=2),
        )

        dashboard_group = Group(header, body)
        border_style = "bold blink green" if is_current else "bright_black"
        return Panel(dashboard_group, title="Player Dashboard", border_style=border_style)

    def _build_log_panel(self, log_entries: Iterable[str]) -> Panel:
        log_lines = list(log_entries)[-4:]
        if not log_lines:
            log_lines = ["Waiting for actions..."]
        log_table = Table.grid(padding=0)
        for entry in log_lines:
            log_table.add_row(Text(f"• {entry}", style="white"))
        return Panel(log_table, title="Game Activity", border_style="bright_black")

    def _build_turn_timer(self, player_key: str) -> ProgressBar:
        now = time.monotonic()
        if self._turn_player_key != player_key:
            self._turn_player_key = player_key
            self._turn_started_at = now
        elapsed = 0.0
        if self._turn_started_at is not None:
            elapsed = max(0.0, now - self._turn_started_at)
        remaining = max(0.0, 15.0 - elapsed)
        return ProgressBar(total=15.0, completed=remaining, width=18, pulse=False)

    def _render_action_buttons(self, is_current: bool) -> Panel:
        glow = "bold blink green" if is_current else "bright_black"
        actions = Text()
        actions.append("[H] HIT", style="bold green")
        actions.append("\n")
        actions.append("[S] STAND", style="bold red")
        actions.append("\n")
        actions.append("[Q] QUIT", style="bold magenta")
        return Panel(Align.center(actions, vertical="middle"), title="Actions", border_style=glow)

    def _render_confetti(self) -> Text:
        return Text("★ ✦ ✶ ✹ ★", style="bold yellow")

    def _is_winner(self, player_state: dict) -> bool:
        status = str(player_state.get("status", "")).upper()
        return player_state.get("is_winner", False) or status in {"WINNER", "NATURAL BLACKJACK"}

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

    def _render_card_large(self, card: object) -> Text:
        normalized = self._normalize_card(card)
        suit_symbol = SUIT_SYMBOLS.get(normalized.suit, normalized.suit)
        color = SUIT_COLORS.get(suit_symbol, "white")
        rank = normalized.rank
        markup = (
            "┌─────────┐\n"
            f"│ [{color}]{rank:<7}[/{color}] │\n"
            "│         │\n"
            f"│    [{color}]{suit_symbol}[/{color}]    │\n"
            "│         │\n"
            f"│ [{color}]{rank:>7}[/{color}] │\n"
            "└─────────┘"
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
