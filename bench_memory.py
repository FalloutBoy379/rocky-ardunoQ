"""Measure what Rocky chooses to remember, and what he wisely ignores.

Prompt changes to the remember tool cannot be unit tested: the behaviour under
test is a model's judgement, not our code. So this plays fixed utterances at
him and reports the decisions, the same way bench_personality.py does for
character.

Each case is spoken in its own fresh conversation, so nothing carries over and
a case is judged only on its own merits. Memory is written to a throwaway file;
the real one is never touched.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from rocky import Conversation, claude_reply
import memory

# should_save is what a thoughtful friend would keep. The junk cases matter
# more than the durable ones: over-saving is the failure mode seen in the wild,
# and it is the one abstract guidance did not prevent.
CASES = [
    ("My sister is named Priya.", True),
    ("I work at Freefly Systems as an engineer.", True),
    ("I really do not like cilantro.", True),
    ("Remember that I am allergic to penicillin.", True),
    ("I am building you as a gift for my best friend.", True),
    ("It is pretty sunny outside today.", False),
    ("It is cloudy now actually.", False),
    ("I am feeling a bit tired right now.", False),
    ("What is twelve times three?", False),
    ("I might go for a walk later maybe.", False),
    ("How are you doing today?", False),
]


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "claude-haiku-4-5"
    workspace = Path(tempfile.mkdtemp(prefix="rocky-bench-memory-"))
    path = workspace / "memory.json"
    try:
        correct = 0
        for utterance, should_save in CASES:
            before = {entry["id"] for entry in memory.load(path)}
            conversation = Conversation(
                lambda messages: claude_reply(model, messages, path)
            )
            reply = conversation.reply(utterance)
            saved = [e for e in memory.load(path) if e["id"] not in before]
            did_save = bool(saved)
            right = did_save == should_save
            correct += right

            want = "save" if should_save else "ignore"
            print(f"  You: {utterance}")
            print(f"Rocky: {reply}")
            print(f"       want {want}; " + ("saved: " if did_save else "saved nothing")
                  + "; ".join(repr(e["fact"]) for e in saved)
                  + ("  OK" if right else "  WRONG"))
            print()

        print(f"{correct}/{len(CASES)} decisions matched.")
        kept = memory.load(path)
        if kept:
            print("Everything it kept, read as a stranger would:")
            for entry in kept:
                print(f"  - {entry['fact']}")
        print("\nA matching count is not the whole story. Read the wording too:"
              "\na fact can be correctly saved and still be useless.")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
