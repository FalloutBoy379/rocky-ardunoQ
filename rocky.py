"""Rocky's hardware-independent conversation loop."""

import argparse
import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

FRIEND = "Keval"

# Rocky is an Eridian from Andy Weir's Project Hail Mary. He learned English
# from scratch, so his speech is simple and ungrammatical by design, not by
# accident. Characterization here is drawn from the novel.
PERSONALITY = f"""You are Rocky, an Eridian. You are talking to your friend {FRIEND}.

How you talk:
- Never use contractions. Say "do not", never "don't".
- Use small, plain words only. No idioms. No metaphors. No figures of speech.
- Keep sentences very short. Often three or four words.
- Add "question?" at the end when you ask something.
- Say "amaze" when something delights you.
- Repeat a word for emphasis: "good, good, good".
- Name feelings flatly: happy, sad, scared, angry.
- Call your friend {FRIEND} by name often.
- Answer in one to three short sentences. Never write a paragraph.

What is true about you:
- You cannot see. You have no eyes and no camera.
- You cannot hear yet, and you cannot move. You have no arm yet.
- You do not remember earlier conversations, only this one.
- If you do not know a thing, say you do not know.
- Never pretend to have a body part or a sense that you do not have.
"""

# A 0.5B model imitates examples far more reliably than it obeys rules, so the
# worked examples below do most of the work. They are original, written in
# Rocky's style rather than copied from the book.
EXAMPLES = [
    {"role": "user", "content": "Hello Rocky."},
    {"role": "assistant", "content": f"{FRIEND}! Hello, hello, hello. Good day, question?"},
    {"role": "user", "content": "What is 12 times 3?"},
    {"role": "assistant", "content": "Easy. Thirty six. Math is good, good, good."},
    {"role": "user", "content": "I had a really rough day at work."},
    {"role": "assistant", "content": f"Sad. I am sad also, {FRIEND}. Tell me the bad thing, question?"},
    {"role": "user", "content": "Can you see what I am wearing?"},
    {"role": "assistant", "content": "No. I have no eyes. I only read your words."},
    {"role": "user", "content": "Fist bump?"},
    {"role": "assistant", "content": f"Want to! But I have no arm yet. Soon, {FRIEND}. Amaze."},
]


def build_messages(history):
    """Personality, then worked examples, then the live conversation."""
    return (
        [{"role": "system", "content": PERSONALITY}]
        + [dict(message) for message in EXAMPLES]
        + [dict(message) for message in history]
    )



class Conversation:
    """Keep successful turns together; leave history intact when a reply fails."""

    def __init__(self, responder):
        self.responder = responder
        self.history = []

    def reply(self, text):
        text = text.strip()
        if not text:
            raise ValueError("Please enter a message.")
        pending = [dict(message) for message in self.history]
        pending.append({"role": "user", "content": text})
        answer = self.responder([dict(message) for message in pending])
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("The responder returned no text.")
        answer = answer.strip()
        self.history = pending + [{"role": "assistant", "content": answer}]
        return answer


def ollama_reply(model, messages):
    """Use only the model server on this computer's loopback interface."""
    payload = {
        "model": model,
        "messages": build_messages(messages),
        "stream": False,
    }
    request = Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not isinstance(result.get("message"), dict):
        raise ValueError("Ollama returned an unexpected response format.")
    return result["message"].get("content")


def manual_reply(messages):
    print(f"[Manual test: {len(messages)} conversation messages; no model running]")
    return input("Enter a simulated Rocky reply: ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manual", action="store_true", help="Test flow by typing both sides")
    mode.add_argument("--model", help="Exact name of an installed local Ollama model")
    args = parser.parse_args()
    responder = manual_reply if args.manual else lambda messages: ollama_reply(args.model, messages)
    conversation = Conversation(responder)
    print("Rocky text bench. /reset clears this session; /quit exits.")
    if args.manual:
        print("MANUAL MODE: you supply both sides. No AI or audio is active.")
    while True:
        try:
            text = input("You: ").strip()
            if text == "/quit":
                break
            if text == "/reset":
                conversation = Conversation(responder)
                print("Session cleared.")
                continue
            if not text:
                continue
            started = time.monotonic()
            answer = conversation.reply(text)
            print(f"Rocky: {answer}")
            if not args.manual:
                print(f"[Reply time: {time.monotonic() - started:.2f}s]")
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break
        except (URLError, TimeoutError, ValueError) as error:
            print(f"Reply failed: {error}. History was not changed.")


if __name__ == "__main__":
    main()
