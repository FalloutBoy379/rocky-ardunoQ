# Handoff

Written 2026-09-12, at the point where the project moves from the Linux laptop
to the Windows laptop that sits on the same network as the board.

Read `README.md` first for how to run things. This file covers what is true
right now, what is trustworthy, and what to do next.

## Where the project is

Rocky holds good text conversations. He has a personality that holds up, memory
that survives restarts, and he is reachable over Wi-Fi from any machine with a
key. No audio hardware is connected yet.

The goal is a Project Hail Mary desk companion, as a gift for Keval. The build
order is: voice loop first, physical interaction and enclosure only once the
voice loop is reliable.

## Hardware

| Part | State |
| --- | --- |
| Arduino UNO Q, 4 GB / 32 GB | Working. Debian 13, kernel 6.16.7, 4 cores. |
| ReSpeaker Flex XVF3800, 4-mic | Not yet connected. Mode unconfirmed, see below. |
| Dayton Audio DMA45-4 speaker | Not yet connected. |
| Powered USB-C dongle | Not confirmed to exist. This is the blocker. |

**The single most important constraint.** The UNO Q has one USB-C port. It is
currently the console *and* the board's power supply. The ReSpeaker needs that
same port, and in host mode the board sources 5 V out rather than drawing power
in, so a USB-C dongle with power delivery passthrough is required (Arduino's
docs exclude Apple dongles). Until that dongle exists, you can have the console
or the microphone, not both.

**Unconfirmed, and it decides the first audio step.** Seeed ships some XVF3800
variants with I2S firmware rather than USB audio. Plug the array in and run
`cat /proc/asound/cards` on the board. A second card next to `ArduinoImolaHPH`
means it enumerated and you can record immediately. Only `ArduinoImolaHPH` means
it needs reflashing with the USB firmware first.

**Design reason the speaker hangs off the ReSpeaker**, not the board's own
output: the XVF3800 cancels echo only against audio it played itself. Route the
speech synthesis through the board's codec instead and Rocky will hear his own
voice and trigger on it. This directly serves the "must not trigger on his own
speaker" goal.

## Access

The board is `rocky.local` via mDNS, user `arduino`, key-based SSH. It joins
Wi-Fi networks it already knows; `add-wifi.sh` teaches it a new one and must be
run **before** the board moves, because without network there is no way in to
fix the network.

Recovery paths, in order:

1. `adb` over USB. Needs no network at all. On Windows use Google's SDK Platform
   Tools; `usb-shell.sh` is the Linux equivalent. This disappears the day the
   ReSpeaker takes the port.
2. `ROCKY_BACKEND=ollama`, a Rocky who needs no internet.

The API key is at `~/.rocky-env` on the board, sourced by `chat.sh` and
`talk.sh` because a non-interactive ssh command does not read the login profile.

`~/rocky-bench` on the board should be a git checkout of this repo, so updating
is `git pull` rather than copying files.

## What is verified and what is not

Verified by running it:

- SSH over Wi-Fi, key auth, host key checked against the board over USB.
- `ssh`, `rocky-ollama` and `avahi-daemon` all return after a real reboot.
- The board moved between two networks and two operating systems with no code
  change, because it is addressed by name rather than by address.
- 33 unit tests covering the memory store, the history cap, prompt injection and
  command dispatch.
- Personality on `claude-haiku-4-5`: 7 of 7 replies in character, 1.0 to 1.9
  seconds warm. On `qwen2.5:0.5b`: 3 of 6, 2.3 to 3.0 seconds.

**Not verified.** The `remember` tool round trip has never run against the live
API. The tests cover the store and the command path, not Claude choosing to call
the tool. This is the first thing to check.

To check it: `./talk`, say something durable like "my sister is Priya", then
`/memories` to see whether it saved. Then `/quit`, `./talk` again, and ask for
your sister's name. That last step is the real test, because it proves the fact
survived the process ending.

## Things that will bite

- **`bench_personality.py` cannot judge whether a reply sounds like Rocky.** It
  checks contractions, register, length and lost identity. Its first version
  reported 5 of 6 on output a human would have called four failures. Read the
  replies, do not trust the number alone.
- **A 0.5B model cannot hold a persona.** This was measured, not assumed. Do not
  spend time prompt-engineering the local model back to parity.
- **Model families differ in accepted parameters.** Haiku 4.5 rejects
  `output_config` outright while Opus takes an effort level. Changing
  `ROCKY_CLAUDE_MODEL` is not always just a string change.
- **Guardrails over-generalize.** "Never pretend to have a sense you do not have"
  made Rocky refuse to explain why the sky is blue. The fix was an explicit rule
  separating what he cannot perceive from what he does not know. Expect more of
  this shape when the microphone arrives and he can genuinely hear.
- **Latency budget.** The language model is one stage of four. At 1 to 1.9
  seconds it already uses most of a natural conversational pause, before wake
  word, speech recognition and speech synthesis exist.
- **Disk is 4.1 GB free**, not 32. That is the real budget for speech models.

## Open, in rough priority order

1. Confirm the ReSpeaker enumerates, or reflash it. Blocked on the dongle.
2. Verify the `remember` tool against the live API.
3. Password SSH is still enabled on the board, and an API key plus personal
   facts about Keval now sit in plaintext on it.
4. No automatic fallback between the Claude and Ollama backends.
5. Commits are authored `ansh@freeflysystems.com` on a public repo.

## Design decisions worth not relitigating

- `Conversation` takes a `responder` callable. Three backends have been added or
  considered without touching it or its tests. Keep new backends as functions.
- Memory operations in `memory.py` know nothing about how they were invoked, and
  command dispatch sits outside the input loop. The voice front end should
  produce the same intents and touch no memory code.
- Recent turns and durable facts are deliberately separate mechanisms. Twenty
  facts cost about 200 tokens; the conversations they came from cost 20,000.
- The Ollama backend is kept despite being much worse. A degraded Rocky with no
  internet beats no Rocky.
