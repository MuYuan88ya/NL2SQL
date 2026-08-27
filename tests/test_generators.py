import unittest
from deepeye.generators import DynamicICLRetriever, ICLGenerator, DEFAULT_GOLD_EXAMPLES

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

if __name__ == "__main__":
    unittest.main()
