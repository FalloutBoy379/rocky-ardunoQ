# Rocky's memory

## Problem

`Conversation` keeps every turn and resends all of them on each request. Cost
grows with the square of the conversation length, latency grows with it, and a
long-running voice session would eventually exhaust the context window. Clearing
the history to fix that would also erase everything Rocky knows about the person
he is talking to.

These are two different needs wearing one mechanism. Recent turns give
conversational follow-ups. Durable facts give a companion who knows you. Only
the first needs to be a transcript.

## Design

**Recent turns.** `Conversation` keeps the last 20 turns and drops older ones.

**Durable facts.** A JSON list at `~/.rocky-memory.json`, outside the repository
because it is personal data rather than code. Each entry has an `id`, the `fact`
text, and the date added. Facts are injected into the system prompt in their own
block. Twenty facts cost roughly 200 tokens; the conversations they came from
could be 20,000.

**Capture.** Two paths into the same operation:

- A `remember` tool the model calls on its own judgement. Claude only; a 0.5B
  local model cannot drive tool use reliably.
- An explicit command, for when the model's judgement is not trusted or misses
  something.

**Inspection.** Listing and removing facts are part of the feature, not extras.
Automatic capture means entries appear that the user did not ask for, so the
list must be auditable and correctable. This matters more under voice, not less.

## Layering

Memory operations in `memory.py` know nothing about how they were invoked.
A command layer maps a parsed intent onto them. The text loop produces those
intents from `/remember`, `/memories`, `/forget`; a future voice loop produces
the same intents by other means and touches no memory code.

Under voice the `remember` tool likely becomes the main explicit path too,
because "Rocky, remember my sister is Priya" is an ordinary sentence and the
tool already covers being asked. The typed command remains as a determinism
guarantee and a debugging affordance.

## Bounds

- At most 100 facts, oldest dropped first. An unbounded fact list is the same
  growth bug in slower form.
- A fact identical to one already stored is rejected, so repeated mentions in
  conversation do not accumulate duplicates.

## Degraded operation

On the Ollama backend the commands work and facts are still injected. Only
automatic capture is unavailable. Rocky degrades rather than breaks offline.

## Out of scope

Editing a fact in place (remove and re-add covers it), tags, expiry, multiple
users, and any server-side or vector store. All are addable later; none are
needed to learn whether the simple version works.

## Risk

The file holds real personal details in plaintext on a board that currently
accepts password SSH from anything on the local network. The device's security
now protects something that matters.
