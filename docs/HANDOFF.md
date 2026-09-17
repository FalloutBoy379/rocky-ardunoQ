# Handoff

Written 2026-09-12, revised 2026-09-16 once the voice loop existed.

Read `README.md` first for how to run things. This file covers what is true
right now, what is trustworthy, and what to do next.

## Where the project is

**Rocky listens and speaks.** The microphone array is connected and working,
speech recognition and synthesis both run on the board with no network, and
conversations through headphones have been held. He has a personality that
holds up, memory that survives restarts, and he is reachable over Wi-Fi from
any machine with a key.

Not yet done: the Dayton speaker has not been driven, there is no enclosure, and
nothing physical (touch, LEDs, servo) exists.

The goal is a Project Hail Mary desk companion, as a gift for Keval. The build
order is: voice loop first, physical interaction and enclosure only once the
voice loop is reliable.

## Hardware

| Part | State |
| --- | --- |
| Arduino UNO Q, 4 GB / 32 GB | Working. Debian 13, kernel 6.16.7, 4 cores. |
| ReSpeaker Flex XVF3800, 4-mic | Working. Enumerated as USB audio with no firmware change. |
| Dayton Audio DMA45-4 speaker | Working, from the array's JST connector. |
| Powered USB-C dongle | In use. The board runs as a USB host through it. |

**The single most important constraint.** The UNO Q has one USB-C port. It is
currently the console *and* the board's power supply. The ReSpeaker needs that
same port, and in host mode the board sources 5 V out rather than drawing power
in, so a USB-C dongle with power delivery passthrough is required (Arduino's
docs exclude Apple dongles). Until that dongle exists, you can have the console
or the microphone, not both.

**Settled.** The array shipped in USB mode and needed no reflashing. It is now
the board's only sound card:

- Capture: 6 channels, 16 kHz, S16_LE. Channels 0 and 1 are the array's
  processed outputs; 2 to 5 are the raw microphones, ship disabled, and read
  about -75 dBFS. `voice.py` listens on **channel 1**, measured rather than
  assumed: on one desk utterance at equal level, all three recognisers
  transcribed channel 1 correctly and channel 0 mangled the back half of the
  sentence. Worth repeating on more utterances, but three independent models
  agreeing on one sample is reasonable evidence.
- Playback: 2 channels, 16 kHz.
- The onboard `ArduinoImolaHPH` codec no longer appears in `/proc/asound/cards`.
  Unexplained. It does not matter while the array is the output path, but it
  would matter if the array were ever unplugged.

The USB descriptors report `wTerminalType 0x0405 Echo-canceling speakerphone`
on both terminals, which confirms from the device itself that its echo
cancellation applies to audio played through it. Play Rocky's voice anywhere
else and he will hear himself.

Rocky speaks as `en_US-mike-medium` at length_scale 0.9, picked by ear from
eight male voices. Piper's high tier is unusable on this board at 0.21x to
0.28x realtime; every medium voice runs 1.6x to 2.3x. Do not re-litigate this
without listening: `audition.py` plays the shortlist, `--time` reports speed.

Speech models live in `/home/arduino/models`: Silero VAD, sherpa-onnx streaming
Zipformer in two sizes, Moonshine tiny, and Piper `en_US-ryan-low`. They are not
in git; a rebuilt board needs them downloaded again.

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

- The `remember` tool works end to end. It was verified in use, not just tested.
- Memory judgement scores 11 of 11 on `bench_memory.py` after the tool
  description was rewritten. It scored 10 of 11 before, and the live memory file
  had been accumulating junk (the weather, twice, contradicting itself). The
  fix was naming the excluded categories explicitly rather than describing them
  abstractly.

**Not verified.** Whether the 3.5 mm jack and the JST speaker output can be
active simultaneously is undocumented by Seeed and untested. Nor is it known
whether Rocky triggers on his own voice now that he has a speaker rather than
headphones: the array's echo canceller and the software mute have never been
exercised against a real loudspeaker in the room.

## Things that will bite

- **`bench_personality.py` cannot judge whether a reply sounds like Rocky.** It
  checks contractions, register, length and lost identity. Its first version
  reported 5 of 6 on output a human would have called four failures. Read the
  replies, do not trust the number alone.
- **Whisper tiny is not good enough for this room, Moonshine is.** Measured on
  real desk utterances: "Rocky, what are you up to?" became "rocky, what I have
  to" on Whisper and "Rocky, what are you up" on Moonshine, and Moonshine
  decodes in 0.6s against Whisper's 1.4s. Whisper also invents captions from
  room noise. The audio was fine in both cases (peaks 21-25k, no clipping,
  speech starting 0.03s in), so suspect the recogniser before the microphone.
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

1. Confirm Rocky does not answer himself now that he has a loudspeaker. This is
   the hard product requirement and the one thing the speaker changes.
2. Volume is set on every start by `ROCKY_VOLUME` (45 of 60, -15 dB). The 12 V
   external input is not needed: at 79 dB per watt at one metre, a tenth of a
   watt is louder than conversation.
3. Password SSH is still enabled on the board, and an API key plus personal
   facts about Keval now sit in plaintext on it.
4. No automatic fallback between the Claude and Ollama backends.
5. Commits are authored `ansh@freeflysystems.com` on a public repo.

## Enclosure numbers, for when that starts

The DMA45-4 has Fs 151 Hz, Qts 0.56, Vas 0.003 ft3 (0.085 L). Standard sealed
box maths on those gives about 0.14 L for a Qtc of 0.707, usable to roughly
190 Hz; half a litre is smoother and slightly lower. Calculated here, not a
Dayton recommendation, so model before cutting. Rocky needs a sealed volume of
at least ~150 cm3 around the driver and no air leaks. Nothing below 150 Hz means
his voice will sound thin, which for a small alien rock is arguably correct.

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
