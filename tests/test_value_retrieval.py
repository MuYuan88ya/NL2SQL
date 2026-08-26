import os
import sqlite3
import unittest
from deepeye.value_retrieval import ValueRetriever

class TestValueRetriever(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = os.path.join(os.path.dirname(__file__), "test_vr.db")
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
            
        conn = sqlite3.connect(cls.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE products (id INT, name TEXT, category TEXT);")
        cursor.execute("INSERT INTO products VALUES (1, 'Apple iPhone 15 Pro', 'Smartphones');")
        cursor.execute("INSERT INTO products VALUES (2, 'MacBook Pro 16 inch', 'Laptops');")
        cursor.execute("INSERT INTO products VALUES (3, 'Sony PlayStation 5', 'Gaming Consoles');")
        conn.commit()
        conn.close()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_build_index(self):
        vr = ValueRetriever(db_path=self.db_path)
        self.assertTrue(vr.built)
        self.assertGreater(len(vr.index), 0)
        indexed_values = [item["value"] for item in vr.index]
        self.assertIn("Apple iPhone 15 Pro", indexed_values)
        self.assertIn("Smartphones", indexed_values)

    def test_cosine_similarity(self):
        vr = ValueRetriever(db_path=self.db_path)
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(vr._cosine_similarity(v1, v2), 1.0)
        self.assertAlmostEqual(vr._cosine_similarity(v1, v3), 0.0)

    def test_fuzzy_retrieval(self):
        vr = ValueRetriever(db_path=self.db_path)
        results = vr.retrieve("Show me all PlayStation 5 consoles")
        self.assertIn("products.name", results)
        self.assertIn("Sony PlayStation 5", results["products.name"])

        results_cat = vr.retrieve("Which laptops are available?")
        self.assertIn("products.category", results_cat)
        self.assertIn("Laptops", results_cat["products.category"])

if __name__ == "__main__":
    unittest.main()
