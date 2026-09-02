import unittest
from unittest.mock import MagicMock
from deepeye.generators import DynamicICLRetriever, ICLGenerator, DivideAndConquerGenerator, DEFAULT_GOLD_EXAMPLES

class TestGenerators(unittest.TestCase):
    def setUp(self):
        self.retriever = DynamicICLRetriever()

    def test_default_examples_exist(self):
        self.assertGreaterEqual(len(DEFAULT_GOLD_EXAMPLES), 5)

    def test_dynamic_retrieval_student_count(self):
        demos = self.retriever.retrieve("What is the total number of students?", k=2)
        self.assertIn("SELECT COUNT(*)", demos)
        self.assertIn("students", demos)

    def test_dynamic_retrieval_course_department(self):
        demos = self.retriever.retrieve("Show all courses in Physics department", k=2)
        self.assertIn("courses", demos)
        self.assertIn("department", demos)

    def test_custom_example_pool(self):
        custom_pool = [
            {"question": "Find employee salary", "sql": "SELECT salary FROM employees;", "tables": ["employees"]},
            {"question": "Count departments", "sql": "SELECT COUNT(*) FROM depts;", "tables": ["depts"]}
        ]
        retriever = DynamicICLRetriever(examples=custom_pool)
        demos = retriever.retrieve("employee salary details", k=1)
        self.assertIn("SELECT salary FROM employees;", demos)

    def test_dnc_decompose_fallback(self):
        generator = DivideAndConquerGenerator(client=None, model_name="dummy")
        # Test fallback heuristic when client is None
        data = generator.decompose(
            question="Find the student with the highest GPA in each department",
            schema="",
            values={}
        )
        self.assertTrue(data["is_complex"])
        self.assertGreaterEqual(len(data["sub_questions"]), 1)

    def test_dnc_mock_execution(self):
        mock_client = MagicMock()
        def make_choice(text):
            m = MagicMock()
            m.choices = [MagicMock(message=MagicMock(content=text))]
            return m

        mock_client.chat.completions.create.side_effect = [
            make_choice("""{
              "is_complex": true,
              "sub_questions": [
                {"id": 1, "description": "find max gpa", "role": "subquery"},
                {"id": 2, "description": "find student with that gpa", "role": "main"}
              ]
            }"""),
            make_choice("SELECT MAX(gpa) FROM students;"),
            make_choice("SELECT name FROM students WHERE gpa = (SELECT MAX(gpa) FROM students);")
        ]

        generator = DivideAndConquerGenerator(client=mock_client, model_name="dummy")
        sql = generator.generate("Find student with max gpa", "CREATE TABLE students (gpa REAL);", {})
        self.assertIn("SELECT", sql)
        self.assertEqual(mock_client.chat.completions.create.call_count, 3)

if __name__ == "__main__":
    unittest.main()
