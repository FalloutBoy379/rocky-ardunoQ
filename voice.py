"""Rocky's ears and voice: the audio front end around the text conversation.

Three stages, run one at a time so Rocky never hears himself think:

  listen  ALSA capture from the ReSpeaker array, channel 1 only, which is the
          array's own echo-cancelled, beamformed output. Vosk turns it into
          text on the board, with no network. Vosk decides where an
          utterance ends.
  think   The same Conversation and responders as the typed bench.
  speak   Piper turns Rocky's reply into 16 kHz audio, sentence by sentence,
          straight into ALSA playback on the same card, so the array can
          subtract his voice from what it hears next.

While Rocky speaks the microphone is muted in software as well. The array's
echo canceller is good, but "must not trigger on his own speaker" is a hard
requirement and belt and braces are cheap.

Nothing here knows about memory. Spoken phrases become the same commands the
keyboard produces, and go through rocky.handle_command like typed ones.
"""

import argparse
import os
import queue
import re
import subprocess
import sys
import threading
import time
from urllib.error import URLError

import rocky

RATE = 16000
CAPTURE_CHANNELS = 6          # what the array's firmware offers
# Channels 0 and 1 are both processed outputs; 2 to 5 are the raw microphones
# and ship disabled, reading -75 dBFS. Measured on one desk utterance at equal
# level (channel 0 RMS 1055, channel 1 RMS 971), channel 1 transcribed better
# on all three recognisers here, while channel 0 mangled the second half of the
# sentence every time:
#   whisper    ch0 "Can I make clearly?"   ch1 "Can you hear me clearly?"
#   moonshine  ch0 "Can I go make a..."    ch1 "can you hear me clearly"
#   zipformer  ch0 "IN A YEAR MAC LIOL"    ch1 "CAN I HEAR ME CLEARLY"
LISTEN_CHANNEL = 1
FRAME_BYTES = 2 * CAPTURE_CHANNELS
CHUNK_SECONDS = 0.1

# After Rocky speaks, a reply within this window counts as addressed to him
# without repeating the wake word. Conversations have follow-ups.
FOLLOWUP_SECONDS = 8.0

# The array sends a beat of Rocky's own tail end after playback stops. Keep
# the microphone muted for that long after the last sample goes out.
UNMUTE_DELAY = 0.4

# Audio to have in hand before playback starts, and how much ALSA should hold.
# Measured underrun without these: "underrun!!! (at least 123.931 ms long)",
# audible as a stutter mid-sentence.
PREROLL = 0.4
PLAYBACK_BUFFER = 0.5

# The small Vosk model has no proper nouns. These are what it hears when
# someone says the friend's name, measured on synthetic speech and on the
# desk. Only applied to the first word of an utterance, where a name is a
# greeting; "at all" mid-sentence must stay "at all".
NAME_FIXUPS = {
    "level": rocky.FRIEND.lower(),
    "devil": rocky.FRIEND.lower(),
    "cavell": rocky.FRIEND.lower(),
    "that all": rocky.FRIEND.lower(),
    "at all": rocky.FRIEND.lower(),
}

# What speech recognisers make of the wake word. Whisper writes "Roki?",
# Vosk "rocky"; either is the friend calling him.
# What recognisers make of the wake word. "knocky" is what Moonshine writes when
# the initial consonant is soft. Only non-words belong here: adding a real word
# like "lucky" would wake him in the middle of ordinary conversation.
WAKE_SPELLINGS = ("rocky", "roki", "rockie", "rocki", "rockey", "rocke", "knocky")

NUMBER_WORDS = {
    word: index
    for index, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve "
        "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}


def mono_channel(frames, channel=LISTEN_CHANNEL, channels=CAPTURE_CHANNELS):
    """Pick one 16-bit channel out of interleaved capture data."""
    usable = len(frames) - len(frames) % (2 * channels)
    return memoryview(frames[:usable]).cast("h")[channel::channels].tobytes()


def fix_names(text):
    """Repair the friend's name where the recogniser has no word for it."""
    words = text.strip()
    for heard, name in NAME_FIXUPS.items():
        if words.lower() == heard or words.lower().startswith(heard + " "):
            return name + words[len(heard):]
    return words


def addressed(text, wake, in_followup=False):
    """Decide whether an utterance was meant for Rocky and strip the wake word.

    Returns the text to act on, or None when it was not for him. With no wake
    word configured every utterance is for him.
    """
    words = text.strip().lower()
    if not words:
        return None
    if not wake:
        return words
    spellings = WAKE_SPELLINGS if wake.lower() == "rocky" else (wake.lower(),)
    pattern = re.compile(
        r"\b(?:hey |hi |ok |okay )?(?:" + "|".join(map(re.escape, spellings)) + r")\b[,.!?]?\s*"
    )
    match = pattern.search(words)
    if match:
        remainder = (words[:match.start()] + " " + words[match.end():]).strip()
        return remainder or wake.lower()
    return words if in_followup else None


def clean_transcript(text):
    """Drop what Whisper writes when nobody spoke: bracketed captions such as
    "(phone ringing)" or "[music]", and then any punctuation-only remainder."""
    text = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", text)
    text = " ".join(text.split())
    return text if re.search(r"\w", text) else ""


def spoken_number(words):
    """'three' -> 3, '3' -> 3, anything else -> None."""
    words = words.strip()
    if words.isdigit():
        return int(words)
    return NUMBER_WORDS.get(words)


def intent(text):
    """Turn a spoken request into the typed command it means, or leave it alone.

    Only the memory operations that the model cannot do by itself: listing and
    forgetting. Remembering is a full sentence, and the remember tool already
    handles being asked, so it stays with the model.
    """
    words = " ".join(text.lower().split())
    if re.search(r"\b(what do you remember|list (your |the )?memories|what are your memories)\b", words):
        return "/memories"
    match = re.search(r"\bforget (?:number |memory |fact )?(\w+)\b", words)
    if match:
        number = spoken_number(match.group(1))
        if number is not None:
            return f"/forget {number}"
    if re.fullmatch(r"(rocky )?(reset|start over|start again|new conversation)", words):
        return "/reset"
    return text


def save_utterance(directory, chunks):
    """Keep what was heard, as 16 kHz mono WAV, for judging recognisers later."""
    import wave

    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, time.strftime("utt-%H%M%S.wav"))
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(b"".join(chunks))
    return path


def sentences(text):
    """Split a reply where Rocky pauses, so playback can start on the first
    sentence while the next is still being synthesised."""
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]
    return parts or [text.strip()]


class Microphone:
    """Continuous capture from the array with a software mute.

    A thread drains the capture process without pause, because a stalled pipe
    stalls arecord and the array then overruns. Muting just drops the data.
    """

    def __init__(self, device="hw:0,0"):
        self.device = device
        self.chunks = queue.Queue()
        self.muted = threading.Event()
        self.process = None

    def start(self):
        self.process = subprocess.Popen(
            [
                "arecord", "-q", "-D", self.device, "-t", "raw",
                "-f", "S16_LE", "-r", str(RATE), "-c", str(CAPTURE_CHANNELS),
            ],
            stdout=subprocess.PIPE,
        )
        threading.Thread(target=self._pump, daemon=True).start()
        return self

    def _pump(self):
        size = int(RATE * CHUNK_SECONDS) * FRAME_BYTES
        while True:
            data = self.process.stdout.read(size)
            if not data:
                self.chunks.put(None)
                return
            if not self.muted.is_set():
                self.chunks.put(mono_channel(data))

    def mute(self):
        self.muted.set()

    def unmute(self):
        # Anything captured while muted was Rocky, not the friend.
        while not self.chunks.empty():
            try:
                self.chunks.get_nowait()
            except queue.Empty:
                break
        self.muted.clear()

    def read(self, timeout=None):
        return self.chunks.get(timeout=timeout)

    def stop(self):
        if self.process:
            self.process.terminate()


class Listener:
    """Vosk, streaming. Yields one string per finished utterance. The first
    recogniser; kept because it needs nothing but its model directory."""

    def __init__(self, model_dir, microphone, save_dir=None):
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        self.recognizer = KaldiRecognizer(Model(model_dir), RATE)
        self.recognizer.SetWords(False)
        self.microphone = microphone
        self.save_dir = save_dir

    def utterances(self):
        import json

        heard = []
        while True:
            chunk = self.microphone.read()
            if chunk is None:
                return
            heard.append(chunk)
            if self.recognizer.AcceptWaveform(chunk):
                text = json.loads(self.recognizer.Result()).get("text", "").strip()
                if text and self.save_dir:
                    save_utterance(self.save_dir, heard)
                heard = []
                if text:
                    yield text


class SherpaListener:
    """sherpa-onnx streaming Zipformer. Yields one string per finished utterance.

    Faster than Vosk on this CPU by a wide margin, so it gets the spare cores.
    Endpointing is the model's own: an utterance ends after a pause, and the
    stream is reset so the next one starts clean.
    """

    def __init__(self, model_dir, microphone, threads=2, hotwords=None, save_dir=None):
        import glob
        import os

        import sherpa_onnx

        def part(name):
            # Prefer the int8 export: same words, about a third faster here.
            found = sorted(glob.glob(os.path.join(model_dir, f"{name}-*.int8.onnx"))) or sorted(
                glob.glob(os.path.join(model_dir, f"{name}-*.onnx"))
            )
            if not found:
                raise FileNotFoundError(f"no {name} model in {model_dir}")
            return found[0]

        options = {}
        if hotwords:
            options.update(
                decoding_method="modified_beam_search",
                hotwords_file=hotwords,
                hotwords_score=2.0,
            )
        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=os.path.join(model_dir, "tokens.txt"),
            encoder=part("encoder"),
            decoder=part("decoder"),
            joiner=part("joiner"),
            num_threads=threads,
            sample_rate=RATE,
            feature_dim=80,
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=2.0,
            rule2_min_trailing_silence=0.8,
            rule3_min_utterance_length=20.0,
            **options,
        )
        self.microphone = microphone
        self.save_dir = save_dir

    def utterances(self):
        import numpy as np

        recognizer = self.recognizer
        stream = recognizer.create_stream()
        heard = []
        while True:
            chunk = self.microphone.read()
            if chunk is None:
                return
            heard.append(chunk)
            stream.accept_waveform(RATE, np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768)
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)
            if recognizer.is_endpoint(stream):
                text = recognizer.get_result(stream).strip().lower()
                recognizer.reset(stream)
                if text and self.save_dir:
                    save_utterance(self.save_dir, heard)
                heard = []
                if text:
                    yield text


class OfflineListener:
    """A voice activity detector in front of a whole-utterance recogniser.

    Whisper hears better than the streaming models on this CPU but only takes
    finished utterances, and captions silence with sound effects. Silero VAD
    decides where speech starts and stops, so Whisper only ever sees speech,
    and clean_transcript drops what it invents anyway. Costs about half the
    utterance's length again in decode time, on four threads.
    """

    def __init__(self, model_dir, microphone, vad_path, threads=4, save_dir=None):
        import glob

        import sherpa_onnx

        def find(pattern):
            found = sorted(glob.glob(os.path.join(model_dir, pattern)))
            if not found:
                raise FileNotFoundError(f"no {pattern} in {model_dir}")
            return found[0]

        if os.path.exists(os.path.join(model_dir, "preprocess.onnx")):
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_moonshine(
                preprocessor=os.path.join(model_dir, "preprocess.onnx"),
                encoder=find("encode*.onnx"), uncached_decoder=find("uncached_decode*.onnx"),
                cached_decoder=find("cached_decode*.onnx"), tokens=os.path.join(model_dir, "tokens.txt"),
                num_threads=threads,
            )
        else:
            self.recognizer = sherpa_onnx.OfflineRecognizer.from_whisper(
                encoder=find("*encoder.int8.onnx"), decoder=find("*decoder.int8.onnx"),
                tokens=find("*tokens.txt"), num_threads=threads,
            )
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = vad_path
        config.silero_vad.min_silence_duration = 0.6
        config.silero_vad.min_speech_duration = 0.25
        config.silero_vad.max_speech_duration = 15.0
        config.sample_rate = RATE
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=30)
        self.microphone = microphone
        self.save_dir = save_dir

    def utterances(self):
        import numpy as np

        window = 512  # what Silero expects per call at 16 kHz
        pending = np.zeros(0, dtype=np.float32)
        while True:
            chunk = self.microphone.read()
            if chunk is None:
                return
            pending = np.concatenate([pending, np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768])
            while len(pending) >= window:
                self.vad.accept_waveform(pending[:window])
                pending = pending[window:]
            while not self.vad.empty():
                samples = np.asarray(self.vad.front.samples, dtype=np.float32)
                self.vad.pop()
                stream = self.recognizer.create_stream()
                stream.accept_waveform(RATE, samples)
                self.recognizer.decode_stream(stream)
                text = clean_transcript(stream.result.text.strip().lower())
                if self.save_dir:
                    save_utterance(self.save_dir, [(samples * 32767).astype(np.int16).tobytes()])
                if text:
                    yield text


class PiperSpeaker:
    """Piper held in memory, playing each sentence as soon as it exists."""

    def __init__(self, voice_path, device="plughw:0,0", length_scale=1.1):
        from piper import PiperVoice, SynthesisConfig

        self.voice = PiperVoice.load(voice_path)
        self.config = SynthesisConfig(length_scale=length_scale)
        self.device = device
        self.rate = self.voice.config.sample_rate

    def _player(self):
        return subprocess.Popen(
            [
                "aplay", "-q", "-D", self.device, "-t", "raw",
                "-f", "S16_LE", "-r", str(self.rate), "-c", "1",
                # A larger ALSA buffer absorbs a scheduling hiccup. The default
                # is small enough that competing with the recogniser for four
                # cores was emptying it mid-word.
                "-B", str(int(PLAYBACK_BUFFER * 1_000_000)),
            ],
            stdin=subprocess.PIPE,
        )

    def say(self, text):
        """Synthesise and play, holding a head start back before starting.

        Piper runs about 1.8x realtime here, so it can keep ahead of playback,
        but it cannot start ahead of it: aplay begins draining the moment the
        first bytes arrive. Accumulating a little audio first turns a race into
        a margin, at the cost of delaying the first word by the time it takes
        to synthesise that much.
        """
        preroll_bytes = int(self.rate * 2 * PREROLL)
        player = None
        pending = []
        pending_bytes = 0
        try:
            for sentence in sentences(text):
                for chunk in self.voice.synthesize(sentence, self.config):
                    data = chunk.audio_int16_bytes
                    if player is not None:
                        player.stdin.write(data)
                        continue
                    pending.append(data)
                    pending_bytes += len(data)
                    if pending_bytes >= preroll_bytes:
                        player = self._player()
                        player.stdin.write(b"".join(pending))
                        pending = []
            if player is None:
                # Shorter than the head start; nothing to race against.
                player = self._player()
                if pending:
                    player.stdin.write(b"".join(pending))
            player.stdin.close()
            player.wait()
        finally:
            if player is not None and player.poll() is None:
                player.kill()


class EspeakSpeaker:
    """Instant and robotic. The fallback, and arguably on brand for an alien."""

    def __init__(self, device="plughw:0,0", speed=150):
        self.device = device
        self.speed = speed

    def say(self, text):
        synth = subprocess.Popen(
            ["espeak-ng", "-v", "en-us", "-s", str(self.speed), "--stdout"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        player = subprocess.Popen(["aplay", "-q", "-D", self.device], stdin=synth.stdout)
        synth.stdin.write(text.encode("utf-8"))
        synth.stdin.close()
        player.wait()


class VoiceLoop:
    """Wire listening, thinking and speaking together.

    listener yields utterances, speaker.say plays text, microphone has mute and
    unmute. All three are injectable so the loop can be tested with none of the
    audio stack present.
    """

    def __init__(self, listener, speaker, microphone, responder, wake="rocky", log=print):
        self.listener = listener
        self.speaker = speaker
        self.microphone = microphone
        self.responder = responder
        self.wake = wake
        self.log = log
        self.conversation = rocky.Conversation(responder)
        self.last_spoke = None

    def speak(self, text):
        self.log(f"Rocky: {text}")
        self.microphone.mute()
        try:
            self.speaker.say(text)
        finally:
            time.sleep(UNMUTE_DELAY)
            self.microphone.unmute()
            self.last_spoke = time.monotonic()

    def in_followup(self):
        return self.last_spoke is not None and time.monotonic() - self.last_spoke < FOLLOWUP_SECONDS

    def handle(self, heard):
        """One utterance in, possibly one reply out. Returns what Rocky said."""
        self.log(f"Heard: {heard}")
        text = addressed(fix_names(heard), self.wake, self.in_followup())
        if text is None:
            return None
        command = intent(text)
        if command == "/reset":
            self.conversation = rocky.Conversation(self.responder)
            self.speak("New talk. Good, good, good.")
            return "reset"
        output = rocky.handle_command(command)
        if output is not None:
            self.speak(output)
            return output
        started = time.monotonic()
        try:
            answer = self.conversation.reply(text)
        except (URLError, TimeoutError, ValueError) as error:
            self.log(f"Reply failed: {error}")
            self.speak("I cannot think right now. Ask again soon, question?")
            return None
        self.log(f"[Reply time: {time.monotonic() - started:.2f}s]")
        self.speak(answer)
        return answer

    def run(self, greeting=None):
        if greeting:
            self.speak(greeting)
            # Unprompted speech opens no follow-up window: nobody asked him
            # anything, so the next voice in the room is not a reply to him.
            self.last_spoke = None
        for heard in self.listener.utterances():
            self.handle(heard)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--model", help="Exact name of an installed local Ollama model")
    mode.add_argument("--claude", nargs="?", const="claude-haiku-4-5", metavar="MODEL")
    parser.add_argument("--asr", default="/home/arduino/models/sherpa-onnx-streaming-zipformer-en-20M-2023-02-17",
                        help="Recogniser model directory: a sherpa-onnx transducer, or a Vosk model")
    parser.add_argument("--vad", default="/home/arduino/models/silero_vad.onnx",
                        help="Silero VAD model, used in front of whole-utterance recognisers")
    parser.add_argument("--hotwords", default=None,
                        help="sherpa-onnx hotwords file, to bias names the model does not know")
    parser.add_argument("--voice", default="/home/arduino/models/en_US-ryan-low.onnx",
                        help="Piper voice, or 'espeak' for the robotic fallback")
    parser.add_argument("--wake", default="rocky",
                        help="Word that addresses Rocky; 'none' answers everything")
    parser.add_argument("--capture", default="hw:0,0")
    parser.add_argument("--playback", default="plughw:0,0")
    parser.add_argument("--no-greeting", action="store_true")
    parser.add_argument("--save-audio", metavar="DIR", default=None,
                        help="Also write each utterance Rocky heard as a WAV file here")
    args = parser.parse_args()

    if args.claude:
        responder = lambda messages: rocky.claude_reply(args.claude, messages)
    else:
        responder = lambda messages: rocky.ollama_reply(args.model, messages)
    rocky.CAN_HEAR = True

    def log(line):
        print(time.strftime("%H:%M:%S"), line, flush=True)

    log("Loading voice...")
    speaker = EspeakSpeaker(args.playback) if args.voice == "espeak" else PiperSpeaker(args.voice, args.playback)
    log("Loading recogniser...")
    microphone = Microphone(args.capture).start()
    if os.path.exists(os.path.join(args.asr, "preprocess.onnx")) or "whisper" in args.asr:
        listener = OfflineListener(args.asr, microphone, args.vad, save_dir=args.save_audio)
    elif os.path.exists(os.path.join(args.asr, "tokens.txt")):
        listener = SherpaListener(args.asr, microphone, hotwords=args.hotwords, save_dir=args.save_audio)
    else:
        listener = Listener(args.asr, microphone, save_dir=args.save_audio)
    wake = None if args.wake.lower() == "none" else args.wake
    loop = VoiceLoop(listener, speaker, microphone, responder, wake=wake, log=log)
    log(f"Listening on {args.capture}. Say '{wake or 'anything'}' to talk.")
    try:
        loop.run(None if args.no_greeting else f"{rocky.FRIEND}! I can hear now. Amaze.")
    except KeyboardInterrupt:
        pass
    finally:
        microphone.stop()


if __name__ == "__main__":
    sys.exit(main())
