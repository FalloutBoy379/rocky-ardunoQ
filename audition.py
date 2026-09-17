"""Play the same Rocky lines in several voices, so a human can choose.

How synthetic a voice sounds is not measurable from here, so this makes the
comparison easy to hear rather than trying to score it. Run it on the board
with the speaker connected.

    python audition.py               # compare voices
    python audition.py --amaze       # compare ways of writing his exclamation
"""

import argparse
import subprocess
import sys

# Male voices, since that is the shortlist Rocky is being chosen from.
#
# Piper's "high" tier is deliberately absent. Measured twice on this board,
# en_US-ryan-high runs at 0.21x realtime and en_US-lessac-high at 0.28x, four
# to five times slower than speech. Every medium voice manages 1.6x to 2.3x.
# There is no point auditioning a voice that cannot keep up.
VOICES = [
    "en_US-ryan-medium",
    "en_US-lessac-medium",
    "en_US-joe-medium",
    "en_US-john-medium",
    "en_US-bryce-medium",
    "en_US-norman-medium",
    "en_US-mike-medium",
    "en_GB-alan-medium",
]

# Kept short, because a ten-voice audition is long. These are the shapes Rocky
# actually speaks in: a greeting, his exclamation, and a clipped apology. A
# voice that is warm on a long sentence can still sound robotic on "sorry,
# sorry, sorry", and most of what he says is the latter.
LINES = [
    "Keval! Amaze! Amaze! Amaze!",
    "Want to! But no arm yet, Keval. Sorry, sorry, sorry.",
]

# "Amaze" phonemises correctly as a#m'eIz; what varies is the prosody Piper
# gives it, which depends on the punctuation and on what sits beside it.
AMAZE = [
    "Amaze.",
    "Amaze!",
    "Amaze, Keval!",
    "Amaze! Amaze! Amaze!",
    "That is amaze, Keval!",
]


def play(voice, text, device, length_scale):
    from piper import PiperVoice, SynthesisConfig

    if not hasattr(play, "cache"):
        play.cache = {}
    if voice not in play.cache:
        play.cache[voice] = PiperVoice.load(f"/home/arduino/models/{voice}.onnx")
    spoken = play.cache[voice]
    config = SynthesisConfig(length_scale=length_scale)
    audio = b"".join(
        chunk.audio_int16_bytes for chunk in spoken.synthesize(text, config)
    )
    # Synthesise fully, then play. An audition must not stutter, and the
    # difference being judged here is the voice, not the buffering.
    subprocess.run(
        ["aplay", "-q", "-D", device, "-t", "raw", "-f", "S16_LE",
         "-r", str(spoken.config.sample_rate), "-c", "1"],
        input=audio, check=False,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amaze", action="store_true",
                        help="compare ways of writing the exclamation instead")
    parser.add_argument("--voice", default=None, help="only this voice")
    parser.add_argument("--time", action="store_true",
                        help="report speed against realtime instead of only playing")
    parser.add_argument("--length-scale", type=float, default=1.1,
                        help="above 1 is slower; Rocky currently uses 1.1")
    parser.add_argument("--device", default="plughw:0,0")
    args = parser.parse_args()

    voices = [args.voice] if args.voice else VOICES
    if args.time:
        import time as clock
        from piper import PiperVoice, SynthesisConfig
        for voice in voices:
            spoken = PiperVoice.load(f"/home/arduino/models/{voice}.onnx")
            config = SynthesisConfig(length_scale=args.length_scale)
            for _ in spoken.synthesize("warm up", config):
                pass
            started = clock.monotonic()
            total = sum(len(c.audio_int16_bytes)
                        for c in spoken.synthesize(LINES[1], config))
            wall = clock.monotonic() - started
            seconds = total / 2 / spoken.config.sample_rate
            flag = "" if seconds / wall > 1.3 else "   TOO SLOW"
            print(f"  {voice:24s} {spoken.config.sample_rate:5d} Hz  "
                  f"{seconds/wall:.2f}x realtime{flag}")
        return
    if args.amaze:
        for text in AMAZE:
            print(f"  {text!r}", flush=True)
            play(voices[0], text, args.device, args.length_scale)
        return
    for voice in voices:
        print(f"\n=== {voice} (length_scale {args.length_scale}) ===", flush=True)
        for text in LINES:
            print(f"  {text}", flush=True)
            play(voice, text, args.device, args.length_scale)


if __name__ == "__main__":
    main()
