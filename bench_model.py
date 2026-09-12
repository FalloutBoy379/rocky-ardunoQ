"""Measure two real turns on the UNO Q, including follow-up context."""

import json
import time

from rocky import Conversation, ollama_reply


conversation = Conversation(lambda messages: ollama_reply("qwen2.5:0.5b", messages))
for prompt in (
    "My name is Ansh. Say hello in one short sentence.",
    "What is my name? Answer briefly.",
):
    started = time.monotonic()
    response = conversation.reply(prompt)
    print(json.dumps({
        "prompt": prompt,
        "response": response,
        "seconds": round(time.monotonic() - started, 2),
    }), flush=True)
