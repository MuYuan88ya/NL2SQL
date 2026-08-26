import os
import math
import re
from typing import List, Dict, Tuple, Optional, Any
from .utils import get_db_connection

class ValueRetriever:
    """
    Hybrid Semantic & Lexical Value Retriever for Database Grounding.
    Supports Dense Vector Embedding Retrieval + Fast N-gram & Substring Matching.
    """
    def __init__(self, db_path: str, client: Any = None, embedding_model: str = "text-embedding-3-small"):
        self.db_path = db_path
        self.client = client
        self.embedding_model = embedding_model
        self.index: List[Dict[str, Any]] = []
        self.built = False
        if os.path.exists(db_path):
            self.build_index()

    def build_index(self):
        """Scans database TEXT columns and populates the value index."""
        conn = get_db_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        self.index = []
        for table in tables:
            table_name = table['name']
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            text_cols = [col['name'] for col in columns if 'TEXT' in col['type'].upper()]
            
            for col in text_cols:
                cursor.execute(f"SELECT DISTINCT {col} FROM {table_name} WHERE {col} IS NOT NULL LIMIT 500;")
                rows = cursor.fetchall()
                for row in rows:
                    val = str(row[0]).strip()
                    if val:
                        self.index.append({
                            "table": table_name,
                            "column": col,
                            "value": val,
                            "vector": None
                        })
        conn.close()
        
        # If client is provided, compute embeddings for indexed values
        if self.client and hasattr(self.client, "embeddings"):
            try:
                values_to_embed = [item["value"] for item in self.index]
                if values_to_embed:
                    resp = self.client.embeddings.create(
                        model=self.embedding_model,
                        input=values_to_embed
                    )
                    for idx, data in enumerate(resp.data):
                        self.index[idx]["vector"] = data.embedding
            except Exception:
                pass
                
        self.built = True

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def _lexical_similarity(self, text_a: str, text_b: str) -> float:
        """Character-level and token-level Jaccard similarity for lexical fuzzy matching."""
        a, b = text_a.lower().strip(), text_b.lower().strip()
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.85
        # Token overlap
        set_a, set_b = set(a.split()), set(b.split())
        if set_a and set_b:
            intersection = len(set_a.intersection(set_b))
            union = len(set_a.union(set_b))
            if union > 0 and intersection / union >= 0.5:
                return 0.8
        # N-gram overlap
        ngrams_a = {a[i:i+3] for i in range(len(a)-2)} if len(a) >= 3 else {a}
        ngrams_b = {b[i:i+3] for i in range(len(b)-2)} if len(b) >= 3 else {b}
        if ngrams_a and ngrams_b:
            jaccard = len(ngrams_a.intersection(ngrams_b)) / len(ngrams_a.union(ngrams_b))
            return jaccard
        return 0.0

    def retrieve(self, question: str, k: int = 5, min_score: float = 0.5) -> Dict[str, List[str]]:
        """
        Retrieves relevant database values matching query using hybrid semantic + lexical search.
        """
        if not self.built:
            self.build_index()

        retrieved: Dict[str, List[Tuple[str, float]]] = {}
        
        # Dense Vector Search if available
        query_vec = None
        if self.client and hasattr(self.client, "embeddings"):
            try:
                resp = self.client.embeddings.create(
                    model=self.embedding_model,
                    input=[question]
                )
                query_vec = resp.data[0].embedding
            except Exception:
                query_vec = None

        words = re.findall(r'\b\w+\b', question)
        phrases = [question] + [" ".join(words[i:i+n]) for n in range(1, 4) for i in range(len(words)-n+1)]

        for item in self.index:
            key = f"{item['table']}.{item['column']}"
            val = item["value"]
            score = 0.0

            if query_vec and item.get("vector"):
                dense_score = self._cosine_similarity(query_vec, item["vector"])
                score = max(score, dense_score)

            for phrase in phrases:
                lex_score = self._lexical_similarity(phrase, val)
                score = max(score, lex_score)

            if score >= min_score:
                if key not in retrieved:
                    retrieved[key] = []
                retrieved[key].append((val, score))

        final_results: Dict[str, List[str]] = {}
        for key, val_scores in retrieved.items():
            sorted_vals = sorted(val_scores, key=lambda x: x[1], reverse=True)
            final_results[key] = [v[0] for v in sorted_vals[:k]]

        return final_results

