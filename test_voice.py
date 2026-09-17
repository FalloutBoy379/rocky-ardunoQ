import struct
import unittest

import rocky
import voice
from voice import (
    VoiceLoop, addressed, clean_transcript, fix_names, intent, mono_channel, sentences,
    spoken_number,
)


class ChannelTests(unittest.TestCase):
    """The array delivers six interleaved channels; Rocky listens to one.

    These name the channel they extract rather than leaning on the default, so
    that retuning which channel Rocky listens to does not break tests about
    de-interleaving, which is a separate concern.
    """

    def test_picks_the_named_channel_from_interleaved_frames(self):
        frames = struct.pack("<12h", 10, 1, 2, 3, 4, 5, 20, 1, 2, 3, 4, 5)
        self.assertEqual(mono_channel(frames, channel=0), struct.pack("<2h", 10, 20))
        self.assertEqual(mono_channel(frames, channel=1), struct.pack("<2h", 1, 1))
        self.assertEqual(mono_channel(frames, channel=5), struct.pack("<2h", 5, 5))

    def test_a_partial_trailing_frame_is_dropped_not_misaligned(self):
        frames = struct.pack("<12h", 10, 1, 2, 3, 4, 5, 20, 1, 2, 3, 4, 5) + b"\x01\x02"
        self.assertEqual(mono_channel(frames, channel=0), struct.pack("<2h", 10, 20))

    def test_listens_to_a_processed_channel_not_a_raw_microphone(self):
        """Channels 2 to 5 are the raw microphones and ship disabled."""
        self.assertIn(voice.LISTEN_CHANNEL, (0, 1))


class WakeWordTests(unittest.TestCase):
    def test_utterance_without_wake_word_is_ignored(self):
        self.assertIsNone(addressed("what time is it", "rocky"))

    def test_wake_word_is_stripped_wherever_it_sits(self):
        self.assertEqual(addressed("rocky what time is it", "rocky"), "what time is it")
        self.assertEqual(addressed("hey rocky what time is it", "rocky"), "what time is it")
        self.assertEqual(addressed("what time is it rocky", "rocky"), "what time is it")

    def test_wake_word_alone_still_gets_a_reply(self):
        self.assertEqual(addressed("rocky", "rocky"), "rocky")

    def test_followup_window_does_not_need_the_wake_word(self):
        self.assertEqual(addressed("and why", "rocky", in_followup=True), "and why")

    def test_no_wake_word_configured_means_everything_is_for_him(self):
        self.assertEqual(addressed("what time is it", None), "what time is it")

    def test_silence_is_never_addressed(self):
        self.assertIsNone(addressed("   ", None))

    def test_wake_word_inside_another_word_does_not_count(self):
        self.assertIsNone(addressed("the rockyard is closed", "rocky"))

    def test_recogniser_spellings_of_the_wake_word_all_count(self):
        self.assertEqual(addressed("roki? what time is it", "rocky"), "what time is it")
        self.assertEqual(addressed("Rockie, hello", "rocky"), "hello")


class TranscriptTests(unittest.TestCase):
    """Whisper narrates silence. Those captions must never reach the model."""

    def test_bracketed_captions_are_dropped(self):
        self.assertEqual(clean_transcript("(phone ringing)"), "")
        self.assertEqual(clean_transcript("[suspenseful music]"), "")

    def test_words_around_a_caption_survive(self):
        self.assertEqual(clean_transcript("hello (door opens) rocky"), "hello rocky")

    def test_ordinary_speech_is_untouched(self):
        self.assertEqual(clean_transcript("no, i'm not okay."), "no, i'm not okay.")


class NameTests(unittest.TestCase):
    """Vosk small has no word for the friend's name and substitutes one."""

    def test_misheard_name_at_the_start_is_repaired(self):
        self.assertEqual(fix_names("level hello rocky"), "keval hello rocky")
        self.assertEqual(fix_names("that all hello"), "keval hello")

    def test_the_same_words_mid_sentence_are_left_alone(self):
        self.assertEqual(fix_names("i do not like it at all"), "i do not like it at all")
        self.assertEqual(fix_names("the water level is low"), "the water level is low")


class IntentTests(unittest.TestCase):
    """Spoken requests land on the same commands the keyboard produces."""

    def test_asking_what_he_remembers_lists_memories(self):
        self.assertEqual(intent("what do you remember"), "/memories")

    def test_forget_by_spoken_number(self):
        self.assertEqual(intent("forget number three"), "/forget 3")
        self.assertEqual(intent("forget 3"), "/forget 3")

    def test_forget_without_a_number_is_ordinary_speech(self):
        self.assertEqual(intent("forget about it"), "forget about it")

    def test_reset_phrases(self):
        self.assertEqual(intent("start over"), "/reset")
        self.assertEqual(intent("rocky reset"), "/reset")

    def test_ordinary_speech_passes_through_unchanged(self):
        self.assertEqual(intent("Why is the sky blue?"), "Why is the sky blue?")

    def test_spoken_numbers(self):
        self.assertEqual(spoken_number("twelve"), 12)
        self.assertEqual(spoken_number("7"), 7)
        self.assertIsNone(spoken_number("banana"))


class SentenceTests(unittest.TestCase):
    def test_split_at_sentence_ends(self):
        self.assertEqual(
            sentences("Keval! Hello, hello. Good day, question?"),
            ["Keval!", "Hello, hello.", "Good day, question?"],
        )

    def test_text_without_punctuation_is_one_sentence(self):
        self.assertEqual(sentences("good good good"), ["good good good"])


class FakeMicrophone:
    def __init__(self):
        self.events = []

    def mute(self):
        self.events.append("mute")

    def unmute(self):
        self.events.append("unmute")


class FakeSpeaker:
    def __init__(self, microphone):
        self.said = []
        self.microphone = microphone

    def say(self, text):
        self.said.append(text)
        self.microphone.events.append("say")


class LoopTests(unittest.TestCase):
    """The loop is exercised with no audio stack at all."""

    def setUp(self):
        voice.UNMUTE_DELAY = 0
        self.microphone = FakeMicrophone()
        self.speaker = FakeSpeaker(self.microphone)
        self.requests = []

        def responder(messages):
            self.requests.append(messages)
            return "Sky is blue. Science is good, good, good."

        self.loop = VoiceLoop(
            listener=None, speaker=self.speaker, microphone=self.microphone,
            responder=responder, wake="rocky", log=lambda line: None,
        )

    def test_microphone_is_muted_for_the_whole_time_rocky_speaks(self):
        self.loop.handle("rocky why is the sky blue")
        self.assertEqual(self.microphone.events, ["mute", "say", "unmute"])

    def test_utterance_not_for_rocky_reaches_neither_model_nor_speaker(self):
        self.loop.handle("what a nice day")
        self.assertEqual(self.requests, [])
        self.assertEqual(self.speaker.said, [])

    def test_wake_word_is_not_sent_to_the_model(self):
        self.loop.handle("rocky why is the sky blue")
        self.assertEqual(self.requests[0][-1]["content"], "why is the sky blue")

    def test_followup_right_after_rocky_spoke_needs_no_wake_word(self):
        self.loop.handle("rocky why is the sky blue")
        self.loop.handle("and at sunset")
        self.assertEqual(len(self.requests), 2)

    def test_reset_starts_a_fresh_conversation_and_says_so(self):
        self.loop.handle("rocky why is the sky blue")
        self.loop.handle("rocky start over")
        self.assertEqual(self.loop.conversation.history, [])
        self.assertEqual(len(self.speaker.said), 2)

    def test_greeting_does_not_open_the_followup_window(self):
        class OneShotListener:
            def utterances(self):
                yield "what a nice day"

        self.loop.listener = OneShotListener()
        self.loop.run(greeting="Hello.")
        self.assertEqual(self.speaker.said, ["Hello."])
        self.assertEqual(self.requests, [])

    def test_a_failed_reply_is_spoken_as_an_apology_not_a_crash(self):
        def fail(messages):
            raise ValueError("no network")

        self.loop.responder = fail
        self.loop.conversation = rocky.Conversation(fail)
        self.assertIsNone(self.loop.handle("rocky hello"))
        self.assertEqual(len(self.speaker.said), 1)
        self.assertEqual(self.microphone.events, ["mute", "say", "unmute"])


class SensesTests(unittest.TestCase):
    """The prompt must tell Rocky whether he can hear, or he denies it."""

    def tearDown(self):
        rocky.CAN_HEAR = False

    def test_text_bench_rocky_cannot_hear(self):
        rocky.CAN_HEAR = False
        self.assertIn("cannot hear", rocky.build_messages([])[0]["content"])

    def test_voice_rocky_can_hear_and_knows_he_is_read_aloud(self):
        rocky.CAN_HEAR = True
        prompt = rocky.build_messages([])[0]["content"]
        self.assertNotIn("cannot hear", prompt)
        self.assertIn("microphone", prompt)
        self.assertNotIn("{SENSES}", prompt)


if __name__ == "__main__":
    unittest.main()
