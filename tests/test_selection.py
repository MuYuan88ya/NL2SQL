import unittest
from unittest.mock import MagicMock, patch
from deepeye.selection import ConfidenceSelector

class TestConfidenceSelector(unittest.TestCase):
    def setUp(self):
        self.db_path = "school.db"

    def test_empty_and_single_candidate(self):
        selector = ConfidenceSelector(client=None, db_path=self.db_path)
        self.assertEqual(selector.select([], "Show students"), "")
        self.assertEqual(selector.select(["SELECT * FROM students;"], "Show students"), "SELECT * FROM students;")

    @patch("deepeye.selection.execute_sql")
    def test_high_confidence_shortcut(self, mock_exec):
        # 4 out of 5 candidates produce the same execution result [('Alice',), ('Bob',)]
        # 1 candidate produces [('Charlie',)]
        mock_exec.side_effect = [
            [("Alice",), ("Bob",)],
            [("Alice",), ("Bob",)],
            [("Alice",), ("Bob",)],
            [("Alice",), ("Bob",)],
            [("Charlie",)],
        ]

        candidates = [
            "SELECT name FROM students WHERE id <= 2;",
            "SELECT name FROM students LIMIT 2;",
            "SELECT name FROM students WHERE age > 18;",
            "SELECT name FROM students WHERE grade = 'A';",
            "SELECT name FROM students WHERE id = 3;",
        ]

        mock_client = MagicMock()
        selector = ConfidenceSelector(client=mock_client, db_path=self.db_path, threshold=0.6)
        winner = selector.select(candidates, "Show top 2 students")

        # Top cluster confidence is 4/5 = 0.8 > 0.6
        self.assertTrue(selector.last_selection_meta["shortcut"])
        self.assertAlmostEqual(selector.last_selection_meta["confidence"], 0.8)
        self.assertEqual(winner, candidates[0])
        # High confidence shortcut should not invoke LLM
        mock_client.chat.completions.create.assert_not_called()

    @patch("deepeye.selection.execute_sql")
    def test_low_confidence_pairwise_voting_and_win_rate(self, mock_exec):
        # Disagreement: 2 candidates produce result R1 (40%), 2 candidates produce result R2 (40%), 1 produces R3 (20%)
        mock_exec.side_effect = [
            [("Physics",)],
            [("Physics",)],
            [("Chemistry",)],
            [("Chemistry",)],
            [("Biology",)],
        ]

        candidates = [
            "SELECT department FROM courses WHERE id = 1;",  # R1 (Conf: 0.4)
            "SELECT department FROM courses WHERE name = 'Phys';", # R1 (Conf: 0.4)
            "SELECT department FROM courses WHERE id = 2;",  # R2 (Conf: 0.4)
            "SELECT department FROM courses WHERE name = 'Chem';", # R2 (Conf: 0.4)
            "SELECT department FROM courses WHERE id = 3;",  # R3 (Conf: 0.2)
        ]

        # Mock LLM judge responses:
        # In pairwise comparison:
        # Candidate A (R1) vs Candidate B (R2) -> LLM votes for Candidate B ('B')
        # Candidate A (R1) vs Candidate C (R3) -> LLM votes for Candidate A ('A')
        # Candidate B (R2) vs Candidate C (R3) -> LLM votes for Candidate B ('A' since B is first in that pair)
        mock_client = MagicMock()
        def mock_call(messages):
            prompt = messages[0]["content"]
            # If comparing R1 and R2, prefer R2
            if "courses WHERE id = 1" in prompt and "courses WHERE id = 2" in prompt:
                return "B"
            # If comparing R1 and R3, prefer R1
            if "courses WHERE id = 1" in prompt and "courses WHERE id = 3" in prompt:
                return "A"
            # If comparing R2 and R3, prefer R2
            if "courses WHERE id = 2" in prompt and "courses WHERE id = 3" in prompt:
                return "A"
            return "A"

        mock_client.chat.completions.create.side_effect = lambda **kwargs: MagicMock(
            choices=[MagicMock(message=MagicMock(content=mock_call(kwargs["messages"])))]
        )

        selector = ConfidenceSelector(client=mock_client, db_path=self.db_path, threshold=0.6, top_k=3)
        winner = selector.select(candidates, "Which department is this course in?")

        self.assertFalse(selector.last_selection_meta["shortcut"])
        # Top confidence is 0.4 <= 0.6
        self.assertAlmostEqual(selector.last_selection_meta["confidence"], 0.4)
        
        # Verify candidate 2 (courses WHERE id = 2) won because of higher win rate:
        # WinRates:
        # R1: beats R3, loses to R2 -> 1/2 = 0.5. Score = 0.4 * 0.5 = 0.20
        # R2: beats R1, beats R3   -> 2/2 = 1.0. Score = 0.4 * 1.0 = 0.40
        # R3: loses to R1, loses to R2 -> 0/2 = 0.0. Score = 0.2 * 0.0 = 0.0
        self.assertEqual(winner, candidates[2])
        self.assertEqual(selector.last_selection_meta["best_idx"], 1)
        self.assertAlmostEqual(selector.last_selection_meta["win_rates"][1], 1.0)
        self.assertAlmostEqual(selector.last_selection_meta["scores"][1], 0.40)

if __name__ == "__main__":
    unittest.main()
