import json
import tempfile
import unittest
from pathlib import Path

import memory


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "memory.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_reads_as_empty(self):
        self.assertEqual(memory.load(self.path), [])

    def test_added_fact_survives_a_reload(self):
        memory.add_fact("Keval's sister is Priya", self.path)
        self.assertEqual(
            [entry["fact"] for entry in memory.load(self.path)],
            ["Keval's sister is Priya"],
        )

    def test_ids_stay_unique_after_a_removal(self):
        """Reusing an id would make /forget ambiguous against a stale listing."""
        first = memory.add_fact("one", self.path)
        memory.add_fact("two", self.path)
        memory.remove_fact(first["id"], self.path)
        third = memory.add_fact("three", self.path)
        ids = [entry["id"] for entry in memory.load(self.path)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn(third["id"], [first["id"]])

    def test_duplicate_fact_is_rejected(self):
        memory.add_fact("He does not like cilantro", self.path)
        self.assertIsNone(memory.add_fact("He does not like cilantro", self.path))
        self.assertEqual(len(memory.load(self.path)), 1)

    def test_duplicate_check_ignores_case_and_padding(self):
        memory.add_fact("He does not like cilantro", self.path)
        self.assertIsNone(memory.add_fact("  he does NOT like cilantro ", self.path))

    def test_blank_fact_is_rejected(self):
        self.assertIsNone(memory.add_fact("   ", self.path))
        self.assertEqual(memory.load(self.path), [])

    def test_oldest_facts_drop_once_the_cap_is_reached(self):
        for index in range(memory.MAX_FACTS + 5):
            memory.add_fact(f"fact {index}", self.path)
        facts = memory.load(self.path)
        self.assertEqual(len(facts), memory.MAX_FACTS)
        self.assertEqual(facts[0]["fact"], "fact 5")

    def test_removing_a_missing_id_reports_failure(self):
        self.assertFalse(memory.remove_fact(99, self.path))

    def test_prompt_block_is_empty_when_nothing_is_remembered(self):
        self.assertEqual(memory.format_for_prompt([]), "")

    def test_prompt_block_lists_every_fact(self):
        memory.add_fact("His sister is Priya", self.path)
        memory.add_fact("He dislikes cilantro", self.path)
        block = memory.format_for_prompt(memory.load(self.path))
        self.assertIn("His sister is Priya", block)
        self.assertIn("He dislikes cilantro", block)

    def test_corrupt_file_reads_as_empty_rather_than_crashing(self):
        """A damaged memory file must not stop Rocky from talking."""
        self.path.write_text("{ this is not json")
        self.assertEqual(memory.load(self.path), [])

    def test_file_is_not_world_readable(self):
        """It holds personal details on a shared-network device."""
        memory.add_fact("Something personal", self.path)
        self.assertEqual(self.path.stat().st_mode & 0o077, 0)

    def test_saved_file_is_readable_json(self):
        memory.add_fact("A fact", self.path)
        self.assertEqual(len(json.loads(self.path.read_text())), 1)


if __name__ == "__main__":
    unittest.main()
