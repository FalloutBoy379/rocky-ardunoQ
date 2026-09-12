import tempfile
import unittest
from pathlib import Path

import memory
from rocky import MAX_TURNS, Conversation, FRIEND, build_messages, handle_command


class ConversationTests(unittest.TestCase):
    def test_followup_receives_previous_successful_turn(self):
        requests = []

        def responder(messages):
            requests.append(messages)
            return "Ready, friend."

        conversation = Conversation(responder)
        conversation.reply("My name is Ansh.")
        conversation.reply("What is my name?")
        self.assertEqual(requests[1], [
            {"role": "user", "content": "My name is Ansh."},
            {"role": "assistant", "content": "Ready, friend."},
            {"role": "user", "content": "What is my name?"},
        ])

    def test_failed_response_does_not_commit_partial_turn(self):
        def fail(messages):
            messages.clear()
            raise ConnectionError("Network unavailable")

        conversation = Conversation(lambda messages: "Hello!")
        conversation.reply("Hello")
        before = [dict(message) for message in conversation.history]
        conversation.responder = fail
        with self.assertRaises(ConnectionError):
            conversation.reply("How are you?")
        self.assertEqual(conversation.history, before)

    def test_blank_input_does_not_call_responder(self):
        def unexpected(messages):
            self.fail("Blank input must not reach the responder")

        with self.assertRaises(ValueError):
            Conversation(unexpected).reply("  ")

    def test_blank_response_does_not_commit_turn(self):
        conversation = Conversation(lambda messages: "  ")
        with self.assertRaises(ValueError):
            conversation.reply("Hello")
        self.assertEqual(conversation.history, [])


class PromptTests(unittest.TestCase):
    """A small model imitates examples far more reliably than it follows rules,
    so the worked examples must actually reach the model, ahead of live turns."""

    def test_examples_sit_between_personality_and_live_turns(self):
        turns = [{"role": "user", "content": "Hello"}]
        sent = build_messages(turns)
        self.assertEqual(sent[0]["role"], "system")
        self.assertEqual(sent[-1], turns[0])
        self.assertGreater(len(sent), 2, "examples are missing from the prompt")

    def test_examples_alternate_user_and_assistant(self):
        sent = build_messages([])
        roles = [message["role"] for message in sent[1:]]
        self.assertEqual(roles, ["user", "assistant"] * (len(roles) // 2))

    def test_examples_address_the_friend_by_name(self):
        spoken = " ".join(
            message["content"] for message in build_messages([])
            if message["role"] == "assistant"
        )
        self.assertIn(FRIEND, spoken)

    def test_build_messages_does_not_mutate_caller_history(self):
        turns = [{"role": "user", "content": "Hello"}]
        build_messages(turns)
        self.assertEqual(turns, [{"role": "user", "content": "Hello"}])


class HistoryLimitTests(unittest.TestCase):
    """History is capped so cost and latency stop growing with session length."""

    def test_history_stops_growing_at_the_limit(self):
        conversation = Conversation(lambda messages: "Good, good, good.")
        for index in range(MAX_TURNS + 10):
            conversation.reply(f"message {index}")
        self.assertEqual(len(conversation.history), MAX_TURNS * 2)

    def test_the_oldest_turns_are_the_ones_dropped(self):
        conversation = Conversation(lambda messages: "Yes.")
        for index in range(MAX_TURNS + 3):
            conversation.reply(f"message {index}")
        spoken = [m["content"] for m in conversation.history if m["role"] == "user"]
        self.assertEqual(spoken[0], "message 3")
        self.assertEqual(spoken[-1], f"message {MAX_TURNS + 2}")


class MemoryPromptTests(unittest.TestCase):
    def test_remembered_facts_reach_the_system_prompt(self):
        sent = build_messages([], facts="What you remember:\n- His sister is Priya\n")
        self.assertIn("His sister is Priya", sent[0]["content"])

    def test_no_facts_leaves_the_prompt_unchanged(self):
        self.assertEqual(build_messages([])[0], build_messages([], facts="")[0])


class CommandTests(unittest.TestCase):
    """The text loop turns typed input into these calls; voice will do the same
    by other means, so command handling must not live in the input loop."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "memory.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_ordinary_text_is_not_a_command(self):
        self.assertIsNone(handle_command("Hello Rocky", self.path))

    def test_remember_stores_a_fact(self):
        self.assertIsNotNone(handle_command("/remember His sister is Priya", self.path))
        self.assertEqual(
            [e["fact"] for e in memory.load(self.path)], ["His sister is Priya"]
        )

    def test_remember_without_text_explains_itself(self):
        self.assertIn("/remember", handle_command("/remember", self.path))
        self.assertEqual(memory.load(self.path), [])

    def test_memories_lists_stored_facts_with_their_ids(self):
        entry = memory.add_fact("He dislikes cilantro", self.path)
        listing = handle_command("/memories", self.path)
        self.assertIn("He dislikes cilantro", listing)
        self.assertIn(str(entry["id"]), listing)

    def test_memories_says_so_when_empty(self):
        self.assertIsNotNone(handle_command("/memories", self.path))

    def test_forget_removes_by_id(self):
        entry = memory.add_fact("A mistake", self.path)
        handle_command(f"/forget {entry['id']}", self.path)
        self.assertEqual(memory.load(self.path), [])

    def test_forget_a_missing_id_reports_rather_than_crashing(self):
        self.assertIsNotNone(handle_command("/forget 99", self.path))

    def test_forget_without_a_number_reports_rather_than_crashing(self):
        self.assertIsNotNone(handle_command("/forget banana", self.path))


if __name__ == "__main__":
    unittest.main()
