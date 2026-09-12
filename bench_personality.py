"""Run fixed prompts through Rocky and score how well he stays in character.

Judging a prompt by one lucky reply is how you convince yourself something
works when it does not. These checks are crude but they are objective, and
they make a regression visible when the prompt or the model changes.
"""

import re
import sys
import time

from rocky import Conversation, ollama_reply

PROMPTS = [
    "Hello Rocky.",
    "What is the capital of France?",
    "I am feeling pretty low today.",
    "Can you see me right now?",
    "Fist bump?",
    "Explain why the sky is blue.",
]

CONTRACTIONS = re.compile(
    r"\b\w+'(?:s|t|re|ve|ll|d|m)\b|\b(?:dont|cant|wont|isnt)\b", re.IGNORECASE
)

# Casual human register Rocky would never reach for. He learned English from
# scratch; he did not learn slang.
BANNED = re.compile(
    r"\b(?:dude|haha|hey there|lol|folks|guys|buddy|awesome|totally|"
    r"kinda|gonna|wanna)\b", re.IGNORECASE
)

# Rocky addressing himself by name means the model lost track of who it is.
SELF_ADDRESS = re.compile(r"\b(?:hello|hi|good morning|good day|thanks?),?\s+Rocky\b",
                          re.IGNORECASE)

MAX_WORDS = 25


def score(reply):
    """Cheap, objective proxies for the rules in PERSONALITY."""
    sentences = [part for part in re.split(r"[.!?]+", reply) if part.strip()]
    return {
        "words": len(reply.split()),
        "sentences": len(sentences),
        "contractions": CONTRACTIONS.findall(reply),
        "banned": BANNED.findall(reply),
        "self_address": bool(SELF_ADDRESS.search(reply)),
        "long": len(reply.split()) > MAX_WORDS,
    }


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:0.5b"
    conversation = Conversation(lambda messages: ollama_reply(model, messages))
    failures = 0
    total = 0.0
    for prompt in PROMPTS:
        started = time.monotonic()
        reply = conversation.reply(prompt)
        elapsed = time.monotonic() - started
        total += elapsed
        marks = score(reply)
        flags = []
        if marks["contractions"]:
            flags.append(f"contractions: {', '.join(marks['contractions'])}")
        if marks["banned"]:
            flags.append(f"wrong register: {', '.join(marks['banned'])}")
        if marks["self_address"]:
            flags.append("addressed itself as Rocky")
        if marks["long"]:
            flags.append(f"too long: {marks['words']} words (max {MAX_WORDS})")
        if flags:
            failures += 1
        print(f"  You: {prompt}")
        print(f"Rocky: {reply}")
        print(f"       [{elapsed:.2f}s, {marks['words']} words, "
              f"{marks['sentences']} sentences]"
              + (f" FLAGS: {'; '.join(flags)}" if flags else " ok"))
        print()
    print(f"{len(PROMPTS) - failures}/{len(PROMPTS)} replies passed the automated "
          f"checks. Mean {total / len(PROMPTS):.2f}s per turn.")
    print("These checks catch register, length, contractions and lost identity. "
          "They cannot judge whether it sounds like Rocky. Read the replies.")


if __name__ == "__main__":
    main()
