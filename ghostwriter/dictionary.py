"""Your personal dictionary: words Whisper should know how to spell, plus fixes for things it keeps getting wrong."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

DICTIONARY_PATH = Path(__file__).resolve().parent.parent / "dictionary.txt"
FIX_ARROW = "->"

log = logging.getLogger("ghostwriter")


@dataclass
class Dictionary:
    words: list[str] = field(default_factory=list)
    fixes: list[tuple[re.Pattern[str], str]] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> "Dictionary":
        dictionary = cls()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if FIX_ARROW in line:
                heard, wanted = (part.strip() for part in line.split(FIX_ARROW, 1))
                dictionary.fixes += [(_loose_pattern(version), wanted) for version in heard.split(",") if version.strip()]
                dictionary._add_word(wanted)
            else:
                dictionary._add_word(line)
        return dictionary

    @property
    def prompt(self) -> str | None:
        """The word list as a hint for Whisper, which nudges it toward these spellings."""
        return ", ".join(self.words) + "." if self.words else None

    def apply(self, text: str) -> str:
        for pattern, wanted in self.fixes:
            text = pattern.sub(lambda _: wanted, text)
        return text

    def _add_word(self, word: str) -> None:
        if word and word not in self.words:
            self.words.append(word)


def _loose_pattern(phrase: str) -> re.Pattern[str]:
    """Match a phrase as whole words, ignoring case, and with or without spaces or hyphens between its words."""
    words = re.findall(r"\w+", phrase)
    return re.compile(r"\b" + r"[\s-]*".join(map(re.escape, words)) + r"\b", re.IGNORECASE)


class DictionaryFile:
    """Reloads the dictionary whenever the file changes, so edits apply to the next dictation."""

    def __init__(self, path: Path = DICTIONARY_PATH) -> None:
        self.path = path
        self._modified: int | None = None
        self._dictionary = Dictionary()

    def current(self) -> Dictionary:
        try:
            modified = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return Dictionary()
        if modified != self._modified:
            self._dictionary = Dictionary.parse(self.path.read_text(encoding="utf-8"))
            self._modified = modified
            log.info("Dictionary loaded: %d words, %d fixes", len(self._dictionary.words), len(self._dictionary.fixes))
        return self._dictionary
