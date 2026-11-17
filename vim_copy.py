#!/usr/bin/env python3
"""Vim-style selection in native tmux Copy Mode. Python standard library only."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import sys
import unicodedata

from vimcopy.textobjects import select

ROOT = Path(__file__).resolve().parent
INNER = "vim-copy-inner"
AROUND = "vim-copy-around"


class CopyError(Exception):
    """An actionable error that should be shown to the invoking client."""


class UnsupportedText(CopyError):
    """A selection cannot be mapped safely; keep Copy Mode and notify in place."""


def tmux(*args: str) -> str:
    result = subprocess.run(["tmux", *args], capture_output=True, text=True)
    if result.returncode:
        raise CopyError(result.stderr.strip() or "tmux command failed")
    return result.stdout.rstrip("\n")


def option(name: str, default: str) -> str:
    return tmux("show-options", "-gqv", name) or default


def cell_positions(text: str) -> tuple[list[int], int]:
    """Map code points to cells, including CJK and combining marks.

    Complex emoji graphemes are deliberately rejected rather than selecting the
    wrong cells. Native tmux motions remain available for those lines.
    """
    positions: list[int] = []
    column = 0
    previous = 0
    for char in text:
        code = ord(char)
        if (char == "\u200d" or 0xFE00 <= code <= 0xFE0F
                or 0xE0100 <= code <= 0xE01EF or 0x1F3FB <= code <= 0x1F3FF
                or 0x1F1E6 <= code <= 0x1F1FF):
            raise UnsupportedText("complex emoji grapheme on this line; use native selection")
        if unicodedata.combining(char) or unicodedata.category(char) in {"Mn", "Me"}:
            positions.append(previous)
            continue
        previous = column
        positions.append(column)
        column += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return positions, column


@dataclass(frozen=True)
class Position:
    row: int
    column: int


class Screen:
    """Logical text plus a reversible physical-cell map of the frozen screen."""

    def __init__(self, capture: str):
        self.rows: list[str] = []
        self.starts: list[int] = []
        chunks: list[str] = []
        offset = 0
        for line in capture.split("\n"):
            flags, separator, content = line.partition(" ")
            if not separator:
                raise CopyError("capture-pane -F returned an invalid grid row")
            self.rows.append(content)
            self.starts.append(offset)
            chunks.append(content)
            offset += len(content)
            if "W" not in flags:
                chunks.append("\n")
                offset += 1
        self.text = "".join(chunks)

    def offset(self, point: Position) -> int:
        if not 0 <= point.row < len(self.rows):
            raise CopyError("copy cursor is outside the captured screen")
        line = self.rows[point.row]
        cells, width = cell_positions(line)
        if point.column >= width or not cells:
            return self.starts[point.row] + len(line)
        index = bisect_right(cells, point.column) - 1
        while index > 0 and cells[index - 1] == cells[index]:
            index -= 1
        return self.starts[point.row] + index

    def position(self, offset: int) -> Position:
        if not 0 <= offset < len(self.text):
            raise CopyError("selected offset is outside the captured screen")
        row = bisect_right(self.starts, offset) - 1
        index = offset - self.starts[row]
        cells, width = cell_positions(self.rows[row])
        return Position(row, cells[index] if index < len(cells) else width)


@dataclass
class State:
    pane: str
    client: str
    screen: Screen
    cursor: Position
    anchor: Position
    present: bool
    rectangle: bool
    mode: str
    history: int
    height: int
    top: int

    @classmethod
    def read(cls, pane: str, client: str) -> State:
        names = ["pane_in_mode", "copy_cursor_x", "copy_cursor_y", "scroll_position",
                 "pane_height", "selection_present", "selection_start_x",
                 "selection_start_y", "selection_end_x", "selection_end_y",
                 "rectangle_toggle", "selection_mode", "selection_active"]
        values = tmux("display-message", "-p", "-t", pane,
                      "|".join("#{" + name + "}" for name in names)).split("|")
        fields = dict(zip(names, values))
        if fields.get("pane_in_mode") != "1" or not fields.get("copy_cursor_x"):
            raise CopyError("enter native Copy Mode before using this action")
        # -M uses Copy Mode's frozen backing grid, not live output. -F exposes
        # soft wraps; -N/-T retain real spaces without padding unused cells.
        screen = Screen(tmux("capture-pane", "-p", "-M", "-F", "-N", "-T",
                             "-S", "-", "-t", pane))
        history = len(screen.rows) - int(fields["pane_height"])
        cursor = Position(history - int(fields["scroll_position"])
                          + int(fields["copy_cursor_y"]), int(fields["copy_cursor_x"]))
        present = fields["selection_present"] == "1" or fields["selection_active"] == "1"
        anchor = cursor
        if present:
            start = Position(int(fields["selection_start_y"]), int(fields["selection_start_x"]))
            end = Position(int(fields["selection_end_y"]), int(fields["selection_end_x"]))
            anchor = end if cursor == start else start
        return cls(pane, client, screen, cursor, anchor, present,
                   fields["rectangle_toggle"] == "1", fields["selection_mode"],
                   history, int(fields["pane_height"]),
                   history - int(fields["scroll_position"]))

    def commands(self, commands: list[list[str]]) -> None:
        args: list[str] = []
        for command in commands:
            if args:
                args.append(";")
            args.extend(["send-keys", "-t", self.pane, "-X", *command])
        if args:
            tmux(*args)

    def move(self, point: Position, viewport: int | None = None,
             horizontal: bool = True) -> list[list[str]]:
        # goto-line is scroll-relative and retains cursor Y. Starting at the
        # history top resets Y; restore a viewport containing the target.
        top = min(max(self.top if viewport is None else viewport,
                      point.row - self.height + 1), point.row, self.history)
        commands = [["history-top"], ["start-of-line"], ["goto-line", str(self.history - top)]]
        if point.row > top:
            commands.append(["-N", str(point.row - top), "cursor-down"])
        if horizontal:
            cells, width = cell_positions(self.screen.rows[point.row])
            steps = len({cell for cell in cells if cell < point.column}) + max(0, point.column - width)
            if steps:
                commands.append(["-N", str(steps), "cursor-right"])
        return commands

    def reselect(self, anchor: Position, cursor: Position, mode: str) -> None:
        commands = [["clear-selection"], ["rectangle-off"], *self.move(anchor),
                    ["select-line" if mode == "line" else "begin-selection"],
                    *self.move(cursor, horizontal=mode != "line")]
        if mode == "rectangle":
            commands.append(["rectangle-on"])
        self.commands(commands)

    def select_span(self, start: int, end: int, linewise: bool = False) -> None:
        # Resolve both endpoints before changing the original selection.
        first, last = self.screen.position(start), self.screen.position(end - 1)
        if linewise:
            first, last = Position(first.row, 0), Position(last.row, 0)
            tmux("set-option", "-p", "-t", self.pane, "@vim-copy-line-columns", "0,0")
        self.reselect(first, last, "line" if linewise else "char")


def notify(client: str, message: str) -> None:
    args = ["display-message"]
    if client:
        args += ["-c", client]
    tmux(*args, "vim-copy: " + message)


def visual(state: State, mode: str) -> None:
    current = "rectangle" if state.rectangle else state.mode
    if state.present and current == mode:
        state.commands([["rectangle-off"], ["clear-selection"]])
        return
    anchor, cursor = state.anchor, state.cursor
    if state.present and current == "line":
        columns = tmux("show-options", "-pqv", "-t", state.pane, "@vim-copy-line-columns")
        if columns:
            anchor_x, cursor_x = map(int, columns.split(","))
            anchor = Position(anchor.row, anchor_x)
            cursor = Position(cursor.row, cursor_x)
    if mode == "line":
        tmux("set-option", "-p", "-t", state.pane, "@vim-copy-line-columns",
             f"{anchor.column},{cursor.column}")
    state.reselect(anchor, cursor, mode)


def yank(state: State, line: bool = False) -> None:
    if not state.present and not line:
        tmux("switch-client", "-c", state.client, "-T", "vim-copy-yank")
        return
    commands = []
    if line:
        commands = [["clear-selection"], ["rectangle-off"], ["select-line"]]
    behavior = option("@vim-copy-yank-exit", "on")
    if behavior not in {"on", "off"}:
        raise CopyError("@vim-copy-yank-exit must be on or off")
    commands.append(["copy-pipe-and-cancel" if behavior == "on" else "copy-pipe-no-clear"])
    state.commands(commands)


def motion(state: State, name: str) -> None:
    if name in {"top", "middle", "bottom"}:
        desired = state.cursor.row - {"top": 0, "middle": state.height // 2,
                                      "bottom": state.height - 1}[name]
        state.commands(state.move(state.cursor, max(0, desired), horizontal=state.mode != "line"))
        return
    # Previous word-end motions use the same original word classes as iw/iW.
    text = state.screen.text
    cursor = state.screen.offset(state.cursor)
    index = min(cursor - 1, len(text) - 1)
    while index >= 0 and text[index].isspace():
        index -= 1
    if index < 0:
        return
    if index == cursor - 1 and cursor < len(text) and not text[cursor].isspace():
        def word_class(char: str) -> int:
            return 1 if char.isalnum() or char == "_" or unicodedata.combining(char) else 2
        current_class = word_class(text[cursor])
        while index >= 0 and not text[index].isspace() and (
                name == "previous-WORD-end" or word_class(text[index]) == current_class):
            index -= 1
        while index >= 0 and text[index].isspace():
            index -= 1
    if index >= 0:
        state.commands(state.move(state.screen.position(index), horizontal=state.mode != "line"))


def action(args: argparse.Namespace) -> None:
    state = State.read(args.pane, args.client)
    operation = args.operation
    if operation.startswith("visual-"):
        visual(state, operation.removeprefix("visual-"))
    elif operation == "swap-end":
        if state.present:
            state.commands([["other-end"]])
    elif operation == "object":
        cursor = state.screen.offset(state.cursor)
        span = select(state.screen.text, cursor, args.object_key, args.around)
        if span is None:
            notify(args.client, "no non-empty matching text object; selection unchanged")
        else:
            state.select_span(*span, linewise=args.object_key == "p")
    elif operation in {"yank", "yank-line"}:
        yank(state, operation == "yank-line")
    else:
        motion(state, operation)


def install() -> None:
    capture = tmux("list-commands", "capture-pane")
    if "F" not in capture.split("]", 1)[0]:
        raise CopyError("tmux 3.7+ with capture-pane -F is required")
    # Quote executable paths, not selected terminal text. All action arguments
    # are constants or tmux's shell-quoted pane/client format values.
    launcher = shlex.join([sys.executable, str(ROOT / "vim_copy.py"), "action"])
    base = launcher + " --pane #{q:pane_id} --client #{q:client_name} "
    commands: list[str] = []

    def command(*parts: str) -> None:
        if commands:
            commands.append(";")
        commands.extend(parts)

    def bind(table: str, key: str, operation: str, *extra: str) -> None:
        payload = base + shlex.join([operation, *extra])
        command("bind-key", "-T", table, key, "run-shell", payload)

    command("set-window-option", "-g", "mode-keys", "vi")
    for key, operation in [("v", "visual-char"), ("V", "visual-line"),
                           ("C-v", "visual-rectangle"), ("y", "yank")]:
        bind("copy-mode-vi", key, operation)
    swap = option("@vim-copy-swap-key", "O")
    previous = option("@_vim-copy-swap-key", "")
    if previous and previous != swap:
        for line in tmux("list-keys", "-T", "copy-mode-vi").splitlines():
            parts = shlex.split(line)
            table = parts.index("-T")
            if parts[table + 2] == previous and str(ROOT / "vim_copy.py") in line:
                command("unbind-key", "-T", "copy-mode-vi", previous)
    bind("copy-mode-vi", swap, "swap-end")
    command("set-option", "-g", "@_vim-copy-swap-key", swap)
    for key, table in [("i", INNER), ("a", AROUND), ("g", "vim-copy-g"),
                       ("z", "vim-copy-z")]:
        command("bind-key", "-T", "copy-mode-vi", key, "switch-client", "-T", table)
    objects = ["w", "W", "p", '"', "'", "`", "(", ")", "b", "{", "}", "B", "[", "]", "<", ">"]
    for table, around in [(INNER, False), (AROUND, True)]:
        for key in objects:
            extra = ["--object-key", key] + (["--around"] if around else [])
            bind(table, key, "object", *extra)
    bind("vim-copy-yank", "y", "yank-line")
    command("bind-key", "-T", "vim-copy-g", "g",
            "send-keys -X history-top; send-keys -X start-of-line")
    for key, operation in [("e", "previous-word-end"), ("E", "previous-WORD-end")]:
        bind("vim-copy-g", key, operation)
    for key, operation in [("t", "top"), ("z", "middle"), ("b", "bottom")]:
        bind("vim-copy-z", key, operation)
    for table in [INNER, AROUND, "vim-copy-yank", "vim-copy-g", "vim-copy-z"]:
        for key in ["Escape", "C-c", "q", "Any"]:
            command("bind-key", "-T", table, key, "switch-client", "-T", "root")
    tmux(*commands)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install")
    call = sub.add_parser("action")
    call.add_argument("--pane", required=True)
    call.add_argument("--client", required=True)
    call.add_argument("operation", choices=["visual-char", "visual-line", "visual-rectangle",
                      "swap-end", "object", "yank", "yank-line",
                      "previous-word-end", "previous-WORD-end", "top", "middle", "bottom"])
    call.add_argument("--object-key", default="w")
    call.add_argument("--around", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "install":
            install()
        else:
            try:
                action(args)
            except UnsupportedText as error:
                # run-shell displays stderr in a new pane mode, losing the
                # selection we deliberately preserved. Report this in place.
                notify(args.client, str(error))
    except (CopyError, OSError) as error:
        message = str(error)
        print("vim-copy: " + message, file=sys.stderr)
        if args.command == "action":
            try:
                notify(args.client, message)
            except (CopyError, OSError):
                pass  # The invoking client may have detached; stderr still reports it.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
