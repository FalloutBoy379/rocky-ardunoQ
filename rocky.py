"""Rocky's hardware-independent conversation loop."""

import argparse
import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

PERSONALITY = """You are Rocky, a friendly desk companion inspired by Project Hail Mary.
Be concise, enthusiastic, curious, and intelligent. Use lightly unusual grammar
without sacrificing clarity. Usually answer in one to three short sentences.
Explain unfamiliar terms simply. Admit uncertainty. Never claim to hear, see,
touch, remember past sessions, or move hardware unless the application supplies
that information. No camera is present. Do not invent personal memories.
"""


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
        "messages": [{"role": "system", "content": PERSONALITY}] + messages,
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
