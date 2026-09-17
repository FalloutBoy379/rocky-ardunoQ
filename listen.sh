#!/bin/sh
# Run this ON Rocky. Starts the voice loop: microphone in, speaker out.
# talk.sh is the typed equivalent and takes the same variables.
#
# ROCKY_VOICE   Piper voice file, or "espeak" for the instant robotic fallback
# ROCKY_WAKE    word that addresses Rocky, or "none" to answer everything
# ROCKY_ASR     recogniser model directory: Whisper or Moonshine (via sherpa-onnx,
#               behind a VAD), a sherpa-onnx streaming transducer, or a Vosk model
# ROCKY_VOLUME  playback level 0 to 60, set on every start
# ROCKY_PACE    phoneme duration multiplier; below 1 makes Rocky quicker
set -eu

ROCKY_DIR=${ROCKY_DIR:-/home/arduino/rocky-bench}
ROCKY_VENV=${ROCKY_VENV:-/home/arduino/rocky-venv}
ROCKY_BACKEND=${ROCKY_BACKEND:-claude}
ROCKY_MODEL=${ROCKY_MODEL:-qwen2.5:0.5b}
ROCKY_CLAUDE_MODEL=${ROCKY_CLAUDE_MODEL:-claude-haiku-4-5}
# Chosen by ear from an eight-voice audition of Piper's medium tier. The high
# tier is unusable on this board: 0.21x to 0.28x realtime against mike's 1.8x.
ROCKY_VOICE=${ROCKY_VOICE:-/home/arduino/models/en_US-mike-medium.onnx}
ROCKY_PACE=${ROCKY_PACE:-0.9}
ROCKY_WAKE=${ROCKY_WAKE:-rocky}
# Moonshine over Whisper tiny, measured on real desk utterances: more accurate
# and about 2.3x faster to decode (0.6s against 1.4s), which comes straight off
# every reply. Whisper also invents captions like "(door closes)" from room
# noise, which clean_transcript then has to throw away.
ROCKY_ASR=${ROCKY_ASR:-/home/arduino/models/sherpa-onnx-moonshine-tiny-en-int8}

# ALSA does not remember its levels across a reboot, so Rocky would otherwise
# start at whatever was last stored. 45 of 60 is -15 dB, measured audible
# across a desk. The array's amplifier does 10 W into 4 ohm and the DMA45-4 is
# rated 10 W RMS, so there is no headroom at the top of the range: raise this
# knowingly, not by reflex.
ROCKY_VOLUME=${ROCKY_VOLUME:-45}
ROCKY_CARD=${ROCKY_CARD:-0}

if [ -f "$HOME/.rocky-env" ]; then
  set -a
  . "$HOME/.rocky-env"
  set +a
fi

cd "$ROCKY_DIR"

# Both outputs: PCM,0 is the stereo jack and PCM,1 the mono speaker amplifier.
# Failure here is not fatal; a Rocky at the wrong volume beats no Rocky.
for output in 0 1; do
  amixer -c "$ROCKY_CARD" -q sset "PCM,$output" "$ROCKY_VOLUME" unmute 2>/dev/null || true
done

# Vosk and Piper live in the venv, so both backends run through it here.
case "$ROCKY_BACKEND" in
  claude)
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
      echo "listen.sh: no ANTHROPIC_API_KEY. Put it in ~/.rocky-env, or run" >&2
      echo "           ROCKY_BACKEND=ollama listen.sh to use the local model." >&2
      exit 1
    fi
    exec "$ROCKY_VENV/bin/python" voice.py --claude "$ROCKY_CLAUDE_MODEL" \
      --voice "$ROCKY_VOICE" --wake "$ROCKY_WAKE" --asr "$ROCKY_ASR" \
      --length-scale "$ROCKY_PACE" "$@"
    ;;
  ollama)
    exec "$ROCKY_VENV/bin/python" voice.py --model "$ROCKY_MODEL" \
      --voice "$ROCKY_VOICE" --wake "$ROCKY_WAKE" --asr "$ROCKY_ASR" \
      --length-scale "$ROCKY_PACE" "$@"
    ;;
  *)
    echo "listen.sh: ROCKY_BACKEND must be 'claude' or 'ollama', got '$ROCKY_BACKEND'" >&2
    exit 2
    ;;
esac
