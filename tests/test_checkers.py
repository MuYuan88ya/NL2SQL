import os
import sqlite3
import unittest
from deepeye.checkers import SyntaxChecker, JoinChecker, ResultChecker, ToolChain

class TestCheckers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join(os.path.dirname(__file__), "test_temp.db")
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
            
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INT, name TEXT, score INT);")
        cursor.execute("INSERT INTO users VALUES (1, 'Alice', 100);")
        cursor.execute("INSERT INTO users VALUES (2, NULL, NULL);")
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_syntax_checker(self):
        checker = SyntaxChecker()
        valid, err = checker.check("SELECT * FROM users;")
        self.assertTrue(valid)
        
        valid_bad, err_bad = checker.check("SELECT FROM WHERE;")
        self.assertFalse(valid_bad)
        self.assertIn("Syntax Error", err_bad)

    def test_join_checker(self):
        checker = JoinChecker()
        valid, err = checker.check("SELECT * FROM a JOIN b ON a.id = b.id;")
        self.assertTrue(valid)
        
        valid_bad, err_bad = checker.check("SELECT * FROM a JOIN b;")
        self.assertFalse(valid_bad)
        self.assertIn("missing ON", err_bad)

    def test_result_checker_success(self):
        checker = ResultChecker(db_path=self.db_path)
        valid, err = checker.check("SELECT * FROM users WHERE id = 1;")
        self.assertTrue(valid)
        self.assertEqual(err, "")

    def test_result_checker_execution_error(self):
        checker = ResultChecker(db_path=self.db_path)
        valid, err = checker.check("SELECT * FROM non_existent_table;")
        self.assertFalse(valid)
        self.assertIn("SQL Execution Error", err)

    def test_result_checker_empty_result(self):
        checker = ResultChecker(db_path=self.db_path)
        valid, err = checker.check("SELECT * FROM users WHERE score > 9999;")
        self.assertFalse(valid)
        self.assertIn("empty result set", err)

    def test_result_checker_all_null(self):
        checker = ResultChecker(db_path=self.db_path)
        valid, err = checker.check("SELECT name, score FROM users WHERE id = 2;")
        self.assertFalse(valid)
        self.assertIn("all NULL values", err)

if __name__ == "__main__":
    unittest.main()
