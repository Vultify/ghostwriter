"""Your personal dictionary: words Whisper should know how to spell, plus fixes for things it keeps getting wrong."""

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ghostwriter.paths import DICTIONARY_DATES_PATH, DICTIONARY_PATH, STARTER_PATH

FIX_ARROW = "->"

log = logging.getLogger("ghostwriter")


@dataclass
class Dictionary:
    words: list[str] = field(default_factory=list)
    fixes: list[tuple[re.Pattern[str], str]] = field(default_factory=list)
    ignored: int = 0  # fix versions with nothing to match, left out

    @classmethod
    def parse(cls, text: str) -> "Dictionary":
        dictionary = cls()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if FIX_ARROW in line:
                heard, wanted = (part.strip() for part in line.split(FIX_ARROW, 1))
                versions = [version for version in heard.split(",") if version.strip()]
                dictionary.fixes += [(_loose_pattern(version), wanted) for version in versions if _matchable(version)]
                dictionary.ignored += sum(not _matchable(version) for version in versions)
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
        self._text: str | None = None  # the file as last loaded
        self._read_failed = False  # warned about an unreadable file
        self._dictionary = Dictionary()

    def current(self) -> Dictionary:
        if not self.path.exists() and self.starter and self.starter.exists():
            shutil.copyfile(self.starter, self.path)
            log.info("Created %s from %s", self.path.name, self.starter.name)
        # Compared by contents, since two saves in the same Windows clock tick share a modified time.
        try:
            text = self.text()
        except FileNotFoundError:
            return Dictionary()
        except ValueError as error:
            if not self._read_failed:
                log.warning("%s %s", error, "The last version is still in use." if self._text else "Dictating without it.")
                self._read_failed = True
            self._text = None  # read again next time
            return self._dictionary
        self._read_failed = False
        if text != self._text:
            self._dictionary = Dictionary.parse(text)
            self._text = text
            if self._dictionary.ignored:
                log.warning("Ignoring %d fix versions that hear only punctuation or emoji, which would match at every word",
                            self._dictionary.ignored)
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
        line = _fix_entry(heard, write)
        if _normal(line) not in {_normal(entry) for entry in self._entries()}:
            self._append(line)

    def remove_fix(self, heard: str, write: str) -> None:
        self._remove(fix_line(heard, write))

    def change_word(self, old: str, new: str) -> str:
        """Change a word in place, keeping its spot in the file. Returns the new line."""
        return self._replace(old.strip(), _checked(new, "word"))

    def change_fix(self, old_heard: str, old_write: str, heard: str, write: str) -> str:
        """Change a fix in place, keeping its spot in the file. Returns the new line."""
        return self._replace(fix_line(old_heard, old_write), _fix_entry(heard, write))

    def merge(self, text: str) -> tuple[int, int]:
        """Add the words and fixes from another dictionary file that this one doesn't have yet, skipping lines that
        don't fit the format. Returns how many words and fixes were added."""
        lines = self._lines()
        known = {_normal(entry) for entry in self._entries()}
        new_lines, words, fixes = [], 0, 0
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                is_fix = FIX_ARROW in line
                entry = _fix_entry(*line.split(FIX_ARROW, 1)) if is_fix else _checked(line, "word")
            except ValueError:
                continue
            if _normal(entry) in known:
                continue
            known.add(_normal(entry))
            new_lines.append(entry)
            fixes, words = fixes + is_fix, words + (not is_fix)
        if new_lines:  # one write, so a big import doesn't rewrite the file once per line
            self.path.write_text("\n".join([*lines, *new_lines]) + "\n", encoding="utf-8")
        return words, fixes

    def _replace(self, old: str, new: str) -> str:
        if _normal(new) != _normal(old) and _normal(new) in {_normal(entry) for entry in self._entries()}:
            raise ValueError("That's already in your dictionary.")
        lines = self._lines()
        for index, line in enumerate(lines):
            if _normal(line) == _normal(old):
                lines[index] = new
                self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return new
        raise ValueError("That entry isn't in the file anymore. It may have been edited as text.")

    def text(self) -> str:
        """The file's text. Raises ValueError with a plain message when it's held by another program or isn't
        saved as UTF-8, and FileNotFoundError when it's missing."""
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        except (OSError, UnicodeError) as error:
            raise ValueError(f"Couldn't read {self.path.name}. Save it as UTF-8 text, or close the app that has it open "
                             f"({error.__class__.__name__}).") from error

    def _lines(self) -> list[str]:
        self.current()  # makes the file from the starter if it's missing
        try:
            return self.text().splitlines()
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


class AddedDates:
    """When each dictionary entry was added, shown in the app window. Kept in a file of its own, so dictionary.txt
    stays plain text that's easy to edit by hand. An entry it hasn't seen before counts from the day it first does."""

    def __init__(self, path: Path = DICTIONARY_DATES_PATH) -> None:
        self.path = path

    def dates(self, lines: list[str], today: date | None = None) -> dict[str, str]:
        """The day each entry was added, keyed by entry_key. Forgets entries that are gone."""
        saved = self._read()
        first_seen = (today or date.today()).isoformat()
        dates = {entry_key(line): saved.get(entry_key(line), first_seen) for line in lines}
        if dates != saved:
            self._write(dates)
        return dates

    def moved(self, old: str, new: str) -> None:
        """Keep an entry's date when it's changed."""
        saved = self._read()
        if entry_key(old) in saved:
            saved[entry_key(new)] = saved.pop(entry_key(old))
            self._write(saved)

    def _read(self) -> dict[str, str]:
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {key: value for key, value in saved.items() if isinstance(value, str)} if isinstance(saved, dict) else {}

    def _write(self, dates: dict[str, str]) -> None:
        try:
            self.path.write_text(json.dumps(dates, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("Couldn't save the dictionary's dates", exc_info=True)


def fix_line(heard: str, write: str) -> str:
    """A fix as it's written in the file."""
    return f"{heard.strip()} {FIX_ARROW} {write.strip()}"


def _fix_entry(heard: str, write: str) -> str:
    """A fix from the app window or an imported file, checked and written the way the file keeps it."""
    versions = [part.strip() for part in _checked(heard, "what it hears").split(",") if part.strip()]
    if not all(_matchable(version) for version in versions):
        raise ValueError("Each version of what it hears needs a letter or number.")
    return fix_line(", ".join(versions), _checked(write, "what to write"))


def _matchable(version: str) -> bool:
    """Whether a version of what it hears has a word to match. One with only punctuation or emoji would match at
    every word boundary."""
    return re.search(r"\w", version) is not None


def entry_key(line: str) -> str:
    """The same for an entry however it's spaced in the file."""
    return _normal(line)


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
