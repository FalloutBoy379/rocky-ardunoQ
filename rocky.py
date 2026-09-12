"""Rocky's hardware-independent conversation loop."""

import argparse
import json
import os
import time

import memory
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
- You are a clever engineer and you know many facts about the world. Not being
  able to see a thing right now does not mean you do not know about it. Answer
  the question with what you know.
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
    {"role": "user", "content": "Why is the sky blue?"},
    {"role": "assistant", "content": "Air bounces blue light more than red light. So sky looks blue. Science is good, good, good."},
    {"role": "user", "content": "Fist bump?"},
    {"role": "assistant", "content": f"Want to! But I have no arm yet. Soon, {FRIEND}. Amaze."},
]


# Recent turns are resent in full on every request, so an uncapped history makes
# cost grow with the square of the session length and eventually exhausts the
# context window. Twenty turns is ample for conversational follow-ups; anything
# worth keeping longer belongs in memory.py, not in the transcript.
MAX_TURNS = 20


def build_messages(history, facts=""):
    """Personality, then worked examples, then the live conversation."""
    return (
        [{"role": "system", "content": PERSONALITY + ("\n" + facts if facts else "")}]
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
        self.history = (pending + [{"role": "assistant", "content": answer}])[-MAX_TURNS * 2:]
        return answer


def ollama_reply(model, messages, path=memory.DEFAULT_PATH):
    """Use only the model server on this computer's loopback interface."""
    payload = {
        "model": model,
        "messages": build_messages(messages, memory.format_for_prompt(memory.load(path))),
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


REMEMBER_TOOL = {
    "name": "remember",
    "description": (
        "Save one durable fact about the person you are talking to. Use this "
        "when they tell you something lasting about themselves, their "
        "preferences, their projects, or people in their life, and whenever "
        "they ask you to remember something. Do not save passing "
        "conversational detail, questions, or things that are only true right "
        "now. Save one short fact per call, written so it still makes sense "
        "read on its own months later."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "fact": {
                "type": "string",
                "description": "The fact to remember, as one short sentence.",
            }
        },
        "required": ["fact"],
        "additionalProperties": False,
    },
}


def handle_command(text, path=memory.DEFAULT_PATH):
    """Map a typed command onto a memory operation.

    Returns text to show the user, or None when this is not a memory command.
    Deliberately separate from the input loop: a voice front end will produce
    the same intents by other means and must not need its own copy of this.
    """
    text = text.strip()
    if not text.startswith("/"):
        return None
    command, _, argument = text.partition(" ")
    argument = argument.strip()

    if command == "/remember":
        if not argument:
            return "Say what to remember, for example: /remember His sister is Priya"
        entry = memory.add_fact(argument, path)
        if entry is None:
            return "Already remembered, or nothing to remember."
        return f"Remembered ({entry['id']}): {entry['fact']}"

    if command == "/memories":
        facts = memory.load(path)
        if not facts:
            return "Nothing remembered yet."
        listing = "\n".join(f"  {e['id']}. {e['fact']}" for e in facts)
        return f"Remembered facts:\n{listing}\nRemove one with /forget <number>."

    if command == "/forget":
        if not argument.isdigit():
            return "Say which one to forget by number, for example: /forget 3"
        if not memory.remove_fact(int(argument), path):
            return f"There is no memory numbered {argument}."
        return f"Forgotten {argument}."

    return None


def claude_reply(model, messages, path=memory.DEFAULT_PATH):
    """Ask Claude for Rocky's next line, letting him save facts as he goes.

    Effort is not accepted by every model. Haiku 4.5 rejects output_config
    outright, while Opus and Sonnet take an effort level, so the parameter is
    only sent where it is supported. On models that do take it, low effort is
    the documented way to buy back latency: disabling thinking on Opus 5 has
    two known failure modes, and Rocky only ever says three sentences.

    When Rocky decides something is worth remembering he asks for the tool
    instead of answering. We save the fact, hand the outcome back, and he then
    writes his actual reply, so a remembering turn costs two round trips and
    every other turn costs one.
    """
    import anthropic

    sent = build_messages(messages, memory.format_for_prompt(memory.load(path)))
    # An organization-level key does not say which workspace to bill, so the
    # API asks for the workspace in a header. A key created inside a workspace
    # already carries that, and needs nothing here.
    workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
    client = anthropic.Anthropic(
        default_headers={"anthropic-workspace-id": workspace} if workspace else None
    )
    options = {}
    if not model.startswith("claude-haiku"):
        options["output_config"] = {"effort": "low"}

    conversation = sent[1:]
    # A guard, not a workflow: Rocky should need one round of tool calls at
    # most. Without it a model that kept asking would loop forever.
    for _ in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4000,
                system=sent[0]["content"],
                messages=conversation,
                tools=[REMEMBER_TOOL],
                **options,
            )
        except anthropic.AuthenticationError:
            raise ValueError("ANTHROPIC_API_KEY is missing or invalid on this machine.")
        except anthropic.BadRequestError as error:
            raise ValueError(f"The API rejected the request: {error.message}")
        except anthropic.RateLimitError:
            raise ValueError("Rate limited by the API. Wait a moment and try again.")
        except anthropic.APIConnectionError:
            raise ValueError("Could not reach the API. Check Rocky's network.")

        if response.stop_reason == "refusal":
            raise ValueError("The model declined to answer that one.")
        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "remember":
                entry = memory.add_fact(block.input.get("fact", ""), path)
                outcome = (
                    f"Saved: {entry['fact']}" if entry
                    else "Not saved; already known or empty."
                )
            else:
                outcome = f"There is no tool named {block.name}."
            results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": outcome}
            )
        conversation = conversation + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": results},
        ]

    raise ValueError("Rocky kept trying to save things and never answered.")


def manual_reply(messages):
    print(f"[Manual test: {len(messages)} conversation messages; no model running]")
    return input("Enter a simulated Rocky reply: ")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manual", action="store_true", help="Test flow by typing both sides")
    mode.add_argument("--model", help="Exact name of an installed local Ollama model")
    mode.add_argument(
        "--claude",
        nargs="?",
        const="claude-haiku-4-5",
        metavar="MODEL",
        help="Use the Claude API. Needs ANTHROPIC_API_KEY in the environment.",
    )
    args = parser.parse_args()
    if args.manual:
        responder = manual_reply
    elif args.claude:
        responder = lambda messages: claude_reply(args.claude, messages)
    else:
        responder = lambda messages: ollama_reply(args.model, messages)
    conversation = Conversation(responder)
    backend = "manual" if args.manual else (args.claude or args.model)
    print(f"Rocky text bench on {backend}.")
    print("/reset clears this conversation; /quit exits.")
    print("/remember <text>, /memories, /forget <number> manage what Rocky keeps.")
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
            # Command handling lives outside this loop so a voice front end can
            # reach the same operations without a keyboard.
            output = handle_command(text)
            if output is not None:
                print(output)
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
