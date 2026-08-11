import unittest
from deepeye.schema_linking import SchemaLinker

class TestSchemaLinkingClosure(unittest.TestCase):
    def setUp(self):
        self.linker = SchemaLinker(client=None, model_name="dummy")
        # Define sample graph: students <-> enrollments <-> courses
        self.graph = {
            "students": {"enrollments"},
            "courses": {"enrollments"},
            "enrollments": {"students", "courses"},
            "teachers": set()
        }

    def test_relational_closure_adds_intermediate_table(self):
        selected = {"students", "courses"}
        closed = self.linker.compute_relational_closure(selected, self.graph)
        self.assertIn("students", closed)
        self.assertIn("courses", closed)
        self.assertIn("enrollments", closed)

    def test_single_table_closure(self):
        selected = {"students"}
        closed = self.linker.compute_relational_closure(selected, self.graph)
        self.assertEqual(closed, {"students"})

    def test_schema_string_fk_parsing(self):
        sample_schema = """
        CREATE TABLE students (
            student_id INTEGER PRIMARY KEY,
            name TEXT
        );

        CREATE TABLE courses (
            course_id INTEGER PRIMARY KEY,
            course_name TEXT
        );

        CREATE TABLE enrollments (
            enrollment_id INTEGER PRIMARY KEY,
            student_id INTEGER,
            course_id INTEGER,
            FOREIGN KEY (student_id) REFERENCES students (student_id),
            FOREIGN KEY (course_id) REFERENCES courses (course_id)
        );
        """
        graph = self.linker._build_fk_graph(sample_schema)
        self.assertIn("students", graph["enrollments"])
        self.assertIn("courses", graph["enrollments"])
        self.assertIn("enrollments", graph["students"])
        self.assertIn("enrollments", graph["courses"])

        selected = {"students", "courses"}
        closed = self.linker.compute_relational_closure(selected, graph)
        self.assertEqual(closed, {"students", "courses", "enrollments"})

if __name__ == "__main__":
    unittest.main()
