# Rocky: a desk assistant on the Arduino UNO Q

Rocky is a standalone conversational desk companion inspired by Project Hail
Mary. He listens through a four-microphone array, answers in his own voice, and
remembers what matters between conversations.

## Talk to Rocky out loud

On the board:

```bash
cd ~/rocky-bench && ./listen.sh
```

Say "Rocky" to get his attention, then talk normally. For about eight seconds
after he finishes you can reply without saying his name again, because
conversations have follow-ups. Speech recognition and synthesis both run on the
board; only the language model uses the network.

Playback volume is set on every start from `ROCKY_VOLUME` (default 45 of 60,
which is -15 dB and audible across a desk), because ALSA does not remember
levels across a reboot. The array's amplifier does 10 W into 4 ohm and the
DMA45-4 is rated 10 W RMS, so the top of the range is the driver's limit with
no margin.

Audio goes in and out through the ReSpeaker array, never the board's own codec.
That is not a preference: the array cancels echo only against audio it played
itself, so routing his voice elsewhere makes him hear and answer himself.

## Talk to Rocky by typing

```bash
cd /home/ansh/Documents/ChatGPT/Rocky
./chat.sh
```

Type a message and wait for the reply. `/reset` clears the conversation and
`/quit` exits. No microphone or speaker is involved yet.

The model server starts at boot, so there is nothing to launch first.
This has been verified across a real reboot. If replies fail, see "When something is not answering" below.

Starting fresh on this project? Read `docs/HANDOFF.md` for current state,
what is verified, and what to do next.

## Talk to Rocky out loud

On the board:

```bash
cd ~/rocky-bench && ./listen.sh
```

Say "Rocky" to get his attention, then talk normally. For about eight seconds
after he finishes you can reply without saying his name again, because
conversations have follow-ups. Speech recognition and synthesis both run on the
board; only the language model uses the network.

Playback volume is set on every start from `ROCKY_VOLUME` (default 45 of 60,
which is -15 dB and audible across a desk), because ALSA does not remember
levels across a reboot. The array's amplifier does 10 W into 4 ohm and the
DMA45-4 is rated 10 W RMS, so the top of the range is the driver's limit with
no margin.

Audio goes in and out through the ReSpeaker array, never the board's own codec.
That is not a preference: the array cancels echo only against audio it played
itself, so routing his voice elsewhere makes him hear and answer himself.

## Talk to Rocky by typing from a shell on the board

Everything already runs on the UNO Q. `chat.sh` only opens a terminal there.
To start Rocky from a shell on the board itself:

```bash
ssh rocky
./talk
```

`talk.sh` loads the API key from `~/.rocky-env`, selects the venv Python, and
honours the same `ROCKY_BACKEND` and `ROCKY_CLAUDE_MODEL` variables. `~/talk`
is a symlink to the copy in `rocky-bench`, so pushing the repo updates it.

## How you reach Rocky

`chat.sh` logs in over Wi-Fi by default. Two transports are available:

| Transport | Command | When to use |
| --- | --- | --- |
| SSH over Wi-Fi (default) | `./chat.sh` | Always. Independent of the USB-C port. |
| USB debug bridge | `ROCKY_TRANSPORT=adb ./chat.sh` | Fallback while the USB-C port is still free. |

**Why this matters.** The UNO Q has a single USB-C port. Right now it runs in
device mode, which is what lets your laptop reach the board over adb (the
Android Debug Bridge, a tool that tunnels a shell over USB). Attaching the
ReSpeaker microphone array requires flipping that port to host mode, where the
board becomes the computer and the array becomes the peripheral. A port does
one of those jobs at a time, so the day the microphone is plugged in, adb over
USB disappears. Arduino's documentation specifies a USB-C dongle with external
power delivery for this, because in host mode the board sources 5 V on VBUS
instead of drawing power from your laptop.

Wi-Fi login is therefore the real channel, and adb is only a convenience.

A `rocky` host alias lives in `~/.ssh/config` on the laptop and resolves
`rocky.local` over mDNS, logging in as `arduino` with your ed25519 key. The
board announces that name itself through `avahi-daemon`, so a new DHCP lease
does not break anything. You can open a shell directly with:

```bash
ssh rocky
```

`chat.sh` reads these variables if you need to override anything:
`ROCKY_TRANSPORT`, `ROCKY_SSH_HOST`, `ROCKY_ADB_SERIAL`, `ROCKY_ADB`,
`ROCKY_DIR`, `ROCKY_MODEL`.

## Understand the two programs

`rocky.py` is the assistant program: it takes your message, adds the
personality instructions and previous conversation, asks the model for a reply,
and prints that reply. This is the file that will later accept speech.

Ollama is the model runner: a separate program that loads Qwen2.5 0.5B and
performs text generation. The local address `127.0.0.1:11434` connects the
Python program to Ollama on the same UNO Q. Your laptop is only the keyboard
and terminal. That address is deliberately loopback-only, so nothing else on
your Wi-Fi network can reach the model server.

The model's parameters are the learned numerical data downloaded from the model
registry. The `0.5B` name means approximately half a billion parameters. This
is a first small-model experiment, not a claim about final assistant quality.

Example: `My name is Ansh` becomes a user message. Rocky's answer is stored
beside it. Asking `What is my name?` sends both earlier messages plus the new
question to the model, so it can use that context to answer. `/reset` removes
the context.

Example: if you ask `Fist bump?`, the model can produce words but cannot move
an arm. That will need a separate hardware command to the UNO Q's
microcontroller. The Linux computer handles conversation; the microcontroller
will later handle physical timing and signals.

## Who answers: Claude or the local model

Rocky has two backends. `chat.sh` uses Claude by default.

| Backend | Command | Notes |
| --- | --- | --- |
| Claude (default) | `./chat.sh` | `claude-haiku-4-5`. Needs Wi-Fi and an API key. |
| Local Ollama | `ROCKY_BACKEND=ollama ./chat.sh` | `qwen2.5:0.5b`. No network needed. |

Override the Claude model with `ROCKY_CLAUDE_MODEL`. Note that `effort` is only
sent to models that accept it: Haiku 4.5 rejects `output_config` outright, so
sending it unconditionally fails every request with a 400.

The API key lives in `~/.rocky-env` on the board and is sourced by `chat.sh`,
because a non-interactive ssh command does not read the login shell's profile.
Use a key created inside a workspace, so it carries a spend limit and can be
revoked on its own. An organization-level key is rejected unless the request
also names a workspace; set `ANTHROPIC_WORKSPACE_ID` in `~/.rocky-env` if you
must use one.

The Python environment for the SDK is a venv at `/home/arduino/rocky-venv`,
because Debian marks the system Python as externally managed.

## Measured performance

Measured on the board over SSH, seconds per conversational turn:

| Backend | Cold first turn | Warm turn | Stayed in character |
| --- | --- | --- | --- |
| `claude-haiku-4-5` | ~6.0 (connection setup) | 1.0 to 1.9 | 7 of 7 |
| `qwen2.5:0.5b` | ~14.4 (model read from disk) | 2.3 to 3.0 | 3 of 6 |

The cloud model is both faster and better. Character scores come from
`bench_personality.py`, which flags contractions, casual register, excessive
length and lost identity. It cannot judge whether a reply sounds like Rocky,
so read the replies too.

This is the language model stage only. Speech recognition and speech synthesis
will add to it.

## Reaching Rocky from a second machine

Each machine needs its own key. Generate the key **on the machine that will
connect**, never on the board: the private half must stay on the laptop, and
only the public half goes to Rocky. `authorized_keys` accumulates, so adding a
machine does not remove another.

On the new machine:

```bash
ssh-keygen -t ed25519          # Windows: same command in PowerShell
cat ~/.ssh/id_ed25519.pub      # Windows: type $env:USERPROFILE\.ssh\id_ed25519.pub
```

Then on the board, paste the line and press Ctrl+D:

```bash
cat >> ~/.ssh/authorized_keys
```

Check it landed as exactly one line starting with `ssh-`. A key broken across
two lines is silently ignored, and you get a password prompt with no
explanation. The same applies to a line missing its `ssh-ed25519` prefix.

On Windows, `adb.exe` from Google's SDK Platform Tools gives the same USB
console as `usb-shell.sh` does on Linux. The UNO Q's USB drivers come with the
Arduino IDE if Windows does not see the board.

## Taking Rocky to another network

Rocky joins Wi-Fi on his own, but only networks he already knows. Teach him a
new one **before** you move him, because without network there is no SSH and no
mDNS to fix it over:

```bash
ssh -t rocky '~/rocky-bench/add-wifi.sh'
```

Run it once per network. Adding your phone's hotspot as well is cheap insurance.
NetworkManager keeps one profile per network and joins whichever it can see, so
a new profile does not disturb the existing one.

`rocky.local` keeps working on any network, because mDNS asks the local network
rather than relying on a fixed address.

If Wi-Fi fails entirely, the USB cable needs no network at all:

```bash
ROCKY_TRANSPORT=adb ./chat.sh          # a shell, to fix the Wi-Fi
ROCKY_BACKEND=ollama ./chat.sh         # a Rocky who works with no internet
```

Some networks block mDNS. If the board is clearly online but `ssh rocky` fails,
read its address over the USB cable with `ip -br addr show wlan0` and put that
in the `rocky` block of `~/.ssh/config` until you are back.

## Managing the board

The model server runs as a systemd service named `rocky-ollama`, defined by
`rocky-ollama.service` in this repository and installed on the board at
`/etc/systemd/system/`. It starts at boot and restarts on failure.

```bash
ssh rocky 'systemctl status rocky-ollama'      # is it healthy
ssh rocky 'journalctl -u rocky-ollama -n 50'   # what did it say
ssh -t rocky 'sudo systemctl restart rocky-ollama'
```

`start-model.sh` remains for running the server by hand in a foreground
terminal. You do not need it in normal use; the service replaces it.

To update Rocky's code on the board after editing it here:

```bash
scp rocky.py rocky:/home/arduino/rocky-bench/rocky.py
```

Then restart the chat program. The personality instructions are near the top of
`rocky.py` in `PERSONALITY`. The board and laptop have separate filesystems:
editing your laptop's copy does not change the board's copy.

Run the tests on the laptop, no board required:

```bash
python3 -m unittest test_rocky.py -v
```

Check what Rocky chooses to remember, on the board:

```bash
ssh rocky 'cd ~/rocky-bench && set -a && . ~/.rocky-env && set +a \
  && /home/arduino/rocky-venv/bin/python bench_memory.py'
```

Eleven fixed utterances, some worth keeping and some not, reported as decisions.
Currently 11 of 11. Read the wording it saved as well as the score: a fact can
be correctly saved and still be useless.

Check how well Rocky holds his character, on the board:

```bash
ssh rocky 'cd /home/arduino/rocky-bench && set -a && . ~/.rocky-env && set +a \
  && /home/arduino/rocky-venv/bin/python bench_personality.py claude-haiku-4-5'
```

## When something is not answering

Work outward from the board:

```bash
ssh rocky 'systemctl is-active rocky-ollama'              # service up?
ssh rocky 'curl -s http://127.0.0.1:11434/api/tags'       # model server answering?
ssh rocky 'journalctl -u rocky-ollama -n 50 --no-pager'   # what went wrong
```

If `ssh rocky` fails, the board is off the network or mDNS is not answering.
Fall back to the USB cable, which does not depend on the network:

```bash
ROCKY_TRANSPORT=adb ./chat.sh
```

To read the board's current address over that same cable:

```bash
/home/ansh/.arduino15/packages/arduino/tools/adb/32.0.0/adb -s 1141166421 shell 'ip -br addr show wlan0'
```

Then update `Hostname` in the `rocky` block of `~/.ssh/config`. Note that
`~/.ssh/known_hosts` is keyed by address too, so the first login at a new
address will warn about an unknown host key. Check the fingerprint matches the
board before accepting it:

```bash
ROCKY_TRANSPORT=adb ./chat.sh   # or an adb shell
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub   # run this on the board
```

## What's installed where

- Laptop project: `/home/ansh/Documents/ChatGPT/Rocky`
- Board Python code: `/home/arduino/rocky-bench`
- Board Ollama runtime: `/home/arduino/rocky-runtime`
- Model data for the current board user: `/home/arduino/.ollama/models`
- Board OS: Debian 13 (trixie), kernel 6.16.7, 4 cores, 3.6 GB RAM
- Runtime: official Ollama v0.34.0 ARM64 archive
- Model: `qwen2.5:0.5b`, Q4_K_M quantization, 398 MB
- Cloud features: disabled by `OLLAMA_NO_CLOUD=1`

The runtime is a manual bench installation in the home partition, not Ollama's
system-wide installer. The archive retains its packaged `bin` and `lib` layout.

## Known issues and open decisions

- **Password logins are still enabled on the board.** Key-based login works, but
  `sshd` will also accept passwords from anything on the Wi-Fi network, and the
  `arduino` account may carry a default password. Worth hardening before Rocky
  lives on a desk permanently.
- **Rocky depends on Wi-Fi now.** The Claude backend needs network and an API
  key. The Ollama backend still runs offline, but its personality is poor. A
  graceful fallback between the two is not implemented.
- **The API key sits in plaintext** in `~/.rocky-env` on the board. Anyone with
  a shell on Rocky has the key. Use a workspace-scoped key with a spend limit.
- **Headphone and speaker at the same time is still untested.** The Dayton works
  from the JST connector; whether the 3.5 mm jack stays live alongside it is
  undocumented by Seeed and has not been tried.
- **The listening channel was wrong until 2026-09-16.** `voice.py` used capture
  channel 0; measured against speech, channel 1 is clearly better and is now
  the default. Based on one utterance across three recognisers, so worth
  repeating.
- **Speech models are not in git.** They live in `/home/arduino/models` and a
  rebuilt board needs them downloaded again.

## Powering the board once the microphone is attached

The UNO Q has a single USB-C connector, and it currently both carries adb and
powers the board from your laptop. Attaching the ReSpeaker needs a USB-C
multiport dongle with power delivery passthrough, and Arduino's documentation
excludes Apple dongles.

The power half is easy to overlook. Arduino states that when the board acts as
a USB host, "it provides 5 V on VBUS to power a connected peripheral", so it is
sourcing power out of that port rather than drawing power in. Plugging the
microphone straight into the board leaves nothing powering the board.

Two lower-confidence points from an Arduino forum thread, not the datasheet,
to confirm against real hardware rather than design around:

- Powering through the VIN pin does not help, because the on-board buck
  converter for VIN reportedly supplies only the board, not the 5 V pins or the
  USB port.
- Booting with USB devices already attached may leave the board in device mode,
  so peripherals may need to be plugged in after boot.

SSH over Wi-Fi is unaffected by any of this. Without a dongle you keep full
access to Rocky and simply cannot attach the microphone.

## Hardware plan

- Compute: Arduino UNO Q, 4 GB RAM / 32 GB storage
- Microphone: Seeed ReSpeaker Flex XVF3800, circular 4-mic array, over USB
- Speaker: Dayton Audio DMA45-4, 1.5 inch, 4 ohm, driven from the ReSpeaker's
  onboard amplifier so that echo cancellation has a valid reference signal
- No camera. USB-C powered, no battery. Physical microphone mute in the final
  enclosure.

## App Lab and Docker

Arduino App Lab is another way to build and deploy programs to the board. Its
Apps can combine Python, a microcontroller sketch, and packaged services called
Bricks. Docker images contain the software environments those services use.
We run this bench program directly on Linux for now. It is not yet an App Lab
app, and no microcontroller sketch is needed for typed conversations.
