"""Your personal dictionary: words Whisper should know how to spell, plus fixes for things it keeps getting wrong."""

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ghostwriter.paths import DICTIONARY_PATH, STARTER_PATH

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

    def __init__(self, path: Path = DICTIONARY_PATH, starter: Path | None = STARTER_PATH) -> None:
        self.path = path
        self.starter = starter
        self._modified: int | None = None
        self._dictionary = Dictionary()

    def current(self) -> Dictionary:
        if not self.path.exists() and self.starter and self.starter.exists():
            shutil.copyfile(self.starter, self.path)
            log.info("Created %s from %s", self.path.name, self.starter.name)
        try:
            modified = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return Dictionary()
        if modified != self._modified:
            self._dictionary = Dictionary.parse(self.path.read_text(encoding="utf-8"))
            self._modified = modified
            log.info("Dictionary loaded: %d words, %d fixes", len(self._dictionary.words), len(self._dictionary.fixes))
        return self._dictionary

    # Editing for the app window. Changes are written straight to the file, keeping its notes and layout.

    def entries(self) -> dict[str, list]:
        """The plain words and the fixes, in file order."""
        words, fixes = [], []
        for entry in self._entries():
            if FIX_ARROW in entry:
                heard, wanted = (part.strip() for part in entry.split(FIX_ARROW, 1))
                fixes.append({"heard": heard, "write": wanted})
            else:
                words.append(entry)
        return {"words": words, "fixes": fixes}

    def add_word(self, word: str) -> None:
        word = _checked(word, "word")
        if word not in self._entries():
            self._append(word)

    def remove_word(self, word: str) -> None:
        self._remove(word.strip())

    def add_fix(self, heard: str, write: str) -> None:
        versions = [part.strip() for part in _checked(heard, "what it hears").split(",") if part.strip()]
        line = f"{', '.join(versions)} {FIX_ARROW} {_checked(write, 'what to write')}"
        if _normal(line) not in {_normal(entry) for entry in self._entries()}:
            self._append(line)

    def remove_fix(self, heard: str, write: str) -> None:
        self._remove(f"{heard.strip()} {FIX_ARROW} {write.strip()}")

    def _lines(self) -> list[str]:
        self.current()  # makes the file from the starter if it's missing
        try:
            return self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []

    def _entries(self) -> list[str]:
        return [line.strip() for line in self._lines() if line.strip() and not line.strip().startswith("#")]

    def _append(self, line: str) -> None:
        self.path.write_text("\n".join([*self._lines(), line]) + "\n", encoding="utf-8")

    def _remove(self, entry: str) -> None:
        lines = self._lines()
        kept = [line for line in lines if _normal(line) != _normal(entry)]
        if len(kept) != len(lines):
            self.path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _checked(text: str, what: str) -> str:
    """Trim an entry from the app window and refuse anything that would break the file's format."""
    text = text.strip()
    if not text:
        raise ValueError(f"Type {what} first.")
    if "\n" in text or FIX_ARROW in text or text.startswith("#"):
        raise ValueError(f"The {what} can't contain {FIX_ARROW}, start with #, or span lines.")
    return text


def _normal(line: str) -> str:
    """A line with its spacing evened out, so a fix matches however it was spaced in the file."""
    if FIX_ARROW in line:
        heard, wanted = (part.strip() for part in line.split(FIX_ARROW, 1))
        return ", ".join(part.strip() for part in heard.split(",")) + f" {FIX_ARROW} " + wanted
    return line.strip()
