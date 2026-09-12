import unittest

from rocky import Conversation, FRIEND, build_messages


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


if __name__ == "__main__":
    unittest.main()
