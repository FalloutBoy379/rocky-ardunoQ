"""Rocky's durable memory: a short list of facts about the person he talks to.

Deliberately separate from the conversation. Recent turns give Rocky
conversational follow-ups and are cheap to discard; facts give him someone he
knows and must outlive the conversation they came from. Twenty facts cost about
200 tokens, where the conversations that produced them could be 20,000.

Nothing here knows how it was invoked. A typed command, a tool call from the
model, and a future voice intent all land on the same functions.
"""

import json
import os
from datetime import date
from pathlib import Path

DEFAULT_PATH = Path.home() / ".rocky-memory.json"

# An unbounded fact list is the same growth problem as an unbounded transcript,
# only slower. Oldest facts fall off the end.
MAX_FACTS = 100


def load(path=DEFAULT_PATH):
    """Read the fact list. A missing or damaged file reads as empty.

    Rocky must still be able to talk when his memory file is unreadable, so a
    corrupt file is treated as no memories rather than raised.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            facts = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return []
    if not isinstance(facts, list):
        return []
    return [entry for entry in facts if isinstance(entry, dict) and "fact" in entry]


def save(facts, path=DEFAULT_PATH):
    """Write the fact list, readable only by its owner."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create with restrictive permissions before any content is written, rather
    # than widening then narrowing. The file holds personal details.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(facts, handle, indent=2, ensure_ascii=False)
    os.chmod(path, 0o600)


def _normalise(text):
    return " ".join(text.split()).casefold()


def add_fact(fact, path=DEFAULT_PATH):
    """Store one fact. Returns the stored entry, or None if it was not stored.

    Blank text and anything already remembered are rejected, so a detail
    mentioned repeatedly in conversation does not accumulate duplicates.
    """
    fact = " ".join(fact.split()) if isinstance(fact, str) else ""
    if not fact:
        return None
    facts = load(path)
    if any(_normalise(entry["fact"]) == _normalise(fact) for entry in facts):
        return None
    # Never reuse an id: a stale listing plus a reused id makes /forget delete
    # the wrong thing.
    entry = {
        "id": max((entry.get("id", 0) for entry in facts), default=0) + 1,
        "fact": fact,
        "added": date.today().isoformat(),
    }
    facts.append(entry)
    save(facts[-MAX_FACTS:], path)
    return entry


def remove_fact(fact_id, path=DEFAULT_PATH):
    """Forget one fact by id. Returns whether anything was removed."""
    facts = load(path)
    kept = [entry for entry in facts if entry.get("id") != fact_id]
    if len(kept) == len(facts):
        return False
    save(kept, path)
    return True


def format_for_prompt(facts):
    """Render facts for the system prompt. Empty when there is nothing to say."""
    if not facts:
        return ""
    lines = "\n".join(f"- {entry['fact']}" for entry in facts)
    return f"What you remember about your friend:\n{lines}\n"
