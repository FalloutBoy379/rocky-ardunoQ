# Rocky: a desk assistant on the Arduino UNO Q

Rocky is a standalone conversational desk companion inspired by Project Hail
Mary. Today he holds typed conversations using a model running entirely on the
board. Speech is the next milestone.

## Talk to Rocky

```bash
cd /home/ansh/Documents/ChatGPT/Rocky
./chat.sh
```

Type a message and wait for the reply. `/reset` clears the conversation and
`/quit` exits. No microphone or speaker is involved yet.

The model server is enabled to start at boot, so there is nothing to launch
first. If replies fail, see "When something is not answering" below.

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

A `rocky` host alias lives in `~/.ssh/config` on the laptop and points at the
board's address, `192.168.100.133`, logging in as `arduino` with your ed25519
key. That address comes from DHCP. If the lease moves, edit that one line.
You can open a shell directly with:

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

## Measured performance

Measured on the board over SSH:

| Turn | Seconds | Source |
| --- | --- | --- |
| First turn after boot (cold, model read from disk) | ~14.4 | one `rocky.py` turn |
| Warm turn | 2.3 to 3.0 | `bench_model.py` |

This is the language model stage only. Speech recognition and speech synthesis
will add to it. Keep this number in view when choosing those engines.

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

## When something is not answering

Work outward from the board:

```bash
ssh rocky 'systemctl is-active rocky-ollama'              # service up?
ssh rocky 'curl -s http://127.0.0.1:11434/api/tags'       # model server answering?
ssh rocky 'journalctl -u rocky-ollama -n 50 --no-pager'   # what went wrong
```

If `ssh rocky` itself fails, the board may have taken a new DHCP address.
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
- **No mDNS.** `avahi-daemon` is inactive, so `rocky.local` does not resolve and
  the SSH alias depends on a DHCP address.
- **Personality is weak at 0.5B.** The model frequently answers in generic
  assistant voice ("How can I assist you today?") rather than Rocky's. Model
  size and prompt both need revisiting.
- **Boot persistence is enabled but not yet proven.** `ssh` and `rocky-ollama`
  are both `enabled` and running, but the board has not been rebooted since.
  Verify with `ssh -t rocky 'sudo reboot'`, wait, then
  `ssh rocky 'systemctl is-active ssh rocky-ollama'`.
- **No speech yet.** The ReSpeaker XVF3800 array has not been delivered. Whether
  it arrives in USB audio mode or needs reflashing from I2S firmware is
  unconfirmed and determines the first audio step.

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
