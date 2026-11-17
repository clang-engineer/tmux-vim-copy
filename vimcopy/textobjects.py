"""Pure character-offset text objects for native tmux Copy Mode."""

from __future__ import annotations

from bisect import bisect_right
import unicodedata


_PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}
_ALIASES = {
    ")": "(", "]": "[", "}": "{", ">": "<", "b": "(", "B": "{",
}
_QUOTES = frozenset("\"'`")


def _kind(character: str, big: bool) -> int:
    if character.isspace():
        return 0
    if big or character.isalnum() or character == "_" or unicodedata.combining(character):
        return 1
    return 2


def _run(text: str, position: int, big: bool) -> tuple[int, int]:
    kind = _kind(text[position], big)
    start, end = position, position + 1
    while start and _kind(text[start - 1], big) == kind:
        start -= 1
    while end < len(text) and _kind(text[end], big) == kind:
        end += 1
    return start, end


def _word(
    text: str, cursor: int, big: bool, around: bool, count: int,
) -> tuple[int, int] | None:
    start, end = _run(text, cursor, big)
    trailing_space = around and text[cursor].isspace() and end == len(text)
    if around and text[cursor].isspace():
        # An around object on whitespace includes the next word, or the last
        # word when the whitespace is at the end of the document.
        if end < len(text):
            _, end = _run(text, end, big)
        elif start:
            start, _ = _run(text, start - 1, big)
        else:
            return None
    for _ in range(count - 1):
        following = end
        while following < len(text) and text[following].isspace():
            following += 1
        if following == len(text):
            return None
        _, end = _run(text, following, big)
    if around:
        following = end
        while following < len(text) and text[following].isspace():
            following += 1
        if following != end:
            end = following
        elif not trailing_space:
            while start and text[start - 1].isspace():
                start -= 1
    return start, end


def _paragraph(
    text: str, cursor: int, around: bool, count: int,
) -> tuple[int, int] | None:
    lines = text.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))
    index = bisect_right(starts, cursor) - 1
    blank = [not line.strip() for line in lines]
    if blank[index]:
        following = index
        while following < len(lines) and blank[following]:
            following += 1
        if following < len(lines):
            index = following
        else:
            while index >= 0 and blank[index]:
                index -= 1
            if index < 0:
                return None
    first = index
    while first and not blank[first - 1]:
        first -= 1
    last = index + 1
    while last < len(lines) and not blank[last]:
        last += 1
    for _ in range(count - 1):
        following = last
        while following < len(lines) and blank[following]:
            following += 1
        if following == len(lines):
            return None
        last = following + 1
        while last < len(lines) and not blank[last]:
            last += 1
    if around:
        following = last
        while following < len(lines) and blank[following]:
            following += 1
        if following != last:
            last = following
        else:
            while first and blank[first - 1]:
                first -= 1
    return starts[first], starts[last]


def _quote(
    text: str, cursor: int, quote: str, around: bool, count: int,
) -> tuple[int, int] | None:
    # Quote text objects are line-local, like Vim's quote objects. Other quote
    # types have no special meaning when looking for this particular quote.
    line_start = text.rfind("\n", 0, cursor) + 1
    line_end = text.find("\n", cursor)
    if line_end < 0:
        line_end = len(text)
    positions = []
    position = line_start
    while position < line_end:
        character = text[position]
        if character == "\\":
            position += 2
            continue
        if character == quote:
            positions.append(position)
        position += 1
    pairs = list(zip(positions[::2], positions[1::2]))
    for index, (start, end) in enumerate(pairs):
        if start <= cursor <= end or cursor < start:
            final = index + count - 1
            if final >= len(pairs):
                return None
            end = pairs[final][1]
            if not around:
                start += 1
            else:
                end += 1
            return (start, end) if start < end else None
    return None


def _bracket(
    text: str, cursor: int, opening: str, around: bool, count: int,
) -> tuple[int, int] | None:
    stack: list[tuple[str, int]] = []
    candidates: list[tuple[int, int]] = []
    quote = None
    position = 0
    while position < len(text):
        character = text[position]
        if character == "\\" and text[position + 1:position + 2] != "\n":
            position += 2
            continue
        if quote is not None:
            if character == quote or character == "\n":
                quote = None
        elif character in _QUOTES:
            quote = character
        elif character in _PAIRS:
            stack.append((character, position))
        elif character in _PAIRS.values():
            if not stack or _PAIRS[stack[-1][0]] != character:
                # A crossing/mismatched close invalidates the open nesting;
                # never search backward for a merely plausible partner.
                stack.clear()
            else:
                kind, start = stack.pop()
                if kind == opening and start <= cursor <= position:
                    candidates.append((start, position))
        position += 1
    # Matching pairs finish from the inside out. Count climbs only enclosing
    # pairs of the requested type, not adjacent pairs or other bracket types.
    if count > len(candidates):
        return None
    start, end = candidates[count - 1]
    if around:
        end += 1
    else:
        start += 1
    return (start, end) if start < end else None


def select(
    text: str, cursor: int, object_key: str, around: bool, count: int = 1,
) -> tuple[int, int] | None:
    """Return a half-open text object, or None without changing any state.

    Cursor must address a character, not the position after the final one.
    Counts must be positive and fully satisfiable. Quote counts span successive
    pairs on one logical line; bracket counts climb enclosing same-type pairs.
    Paragraph ranges contain complete nonblank lines, including their newlines.
    """
    if count < 1 or cursor < 0 or cursor >= len(text):
        return None
    if object_key in ("w", "W"):
        return _word(text, cursor, object_key == "W", around, count)
    if object_key == "p":
        return _paragraph(text, cursor, around, count)
    if object_key in _QUOTES:
        return _quote(text, cursor, object_key, around, count)
    opening = _ALIASES.get(object_key, object_key)
    if opening in _PAIRS:
        return _bracket(text, cursor, opening, around, count)
    return None
