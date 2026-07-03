import re
import unicodedata
from pathlib import Path
from typing import Set

_NAMES: Set[str] = set()
_DATA_FILE = Path(__file__).parent.parent / "data" / "french_names.txt"

# Names that appear in both genders — always reject to be safe
_AMBIGUOUS = {
    "camille", "alexis", "claude", "dominique", "charlie", "morgan",
    "remy", "remi", "lou", "sam", "ange", "andrea", "noel",
}


def _normalize(text: str) -> str:
    """Lowercase → strip accents → keep only [a-z]."""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z]", "", text)
    return text


def load_names() -> Set[str]:
    global _NAMES
    if _NAMES:
        return _NAMES
    if _DATA_FILE.exists():
        with open(_DATA_FILE, encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name and not name.startswith("#"):
                    normalized = _normalize(name)
                    if normalized not in _AMBIGUOUS:
                        _NAMES.add(normalized)
    return _NAMES


def is_french_male(username: str) -> bool:
    """
    Returns True if the username contains a French masculine first name.

    Rejects:
    - Usernames with no recognizable name (gamertags like 'xXkiller99Xx')
    - Ambiguous/feminine names
    - Usernames shorter than 3 alpha chars
    """
    names = load_names()
    cleaned = _normalize(username)

    if len(cleaned) < 3:
        return False

    # Reject obvious gamertags: mix of random letters with no name substring
    if cleaned in _AMBIGUOUS:
        return False

    # Direct match
    if cleaned in names:
        return True

    # Substring match (name must be ≥4 chars to avoid false positives)
    for name in names:
        if len(name) >= 4 and name in cleaned:
            return True

    return False
