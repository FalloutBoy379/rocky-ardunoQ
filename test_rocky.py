import unittest

from rocky import Conversation


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


if __name__ == "__main__":
    unittest.main()
