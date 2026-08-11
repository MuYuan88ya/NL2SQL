from typing import List, Dict, Set
from collections import deque
import re
import sqlite3
import sqlglot
from openai import OpenAI
from .utils import PROMPT_DIRECT_LINKING, PROMPT_GENERATE_SKELETON, call_openai_with_retry

class SchemaLinker:
    def __init__(self, client: OpenAI, model_name: str, db_path: str = None):
        self.client = client
        self.model_name = model_name
        self.db_path = db_path

    def link(self, question: str, schema: str, values: Dict[str, List[str]], db_path: str = None) -> str:
        """Combines Direct, Reversed, and Value-based linking with Relational Closure."""
        db_path = db_path or self.db_path

        # 1. Direct Linking
        direct_schema = self._direct_link(question, schema, values)
        
        # 2. Reversed Linking
        reversed_schema = self._reversed_link(question, schema, values)
        
        # 3. Value-based Linking
        value_schema = self._value_based_link(values)
        
        # Union
        candidate_tables = direct_schema.union(reversed_schema).union(value_schema)
        
        # Extract foreign key graph
        fk_graph = self._build_fk_graph(schema, db_path)
        
        # Enforce Relational Closure
        closed_tables = self.compute_relational_closure(candidate_tables, fk_graph)
        
        # Filter schema string to only include relevant tables
        filtered_schema = self._filter_schema_str(schema, closed_tables)
        return filtered_schema

    def _build_fk_graph(self, schema: str, db_path: str = None) -> Dict[str, Set[str]]:
        graph: Dict[str, Set[str]] = {}
        
        # Initialize graph with tables from schema string
        table_names = re.findall(r'CREATE\s+TABLE\s+([a-zA-Z0-9_]+)', schema, re.IGNORECASE)
        for t in table_names:
            graph[t] = set()

        # Method A: Query SQLite PRAGMA if db_path exists
        if db_path:
            try:
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall()]
                for t in tables:
                    if t not in graph:
                        graph[t] = set()
                    cursor.execute(f"PRAGMA foreign_key_list({t})")
                    fks = cursor.fetchall()
                    for fk in fks:
                        target_table = fk[2]
                        graph[t].add(target_table)
                        if target_table not in graph:
                            graph[target_table] = set()
                        graph[target_table].add(t)
                conn.close()
                return graph
            except Exception:
                pass

        # Method B: Regex parsing schema string for FOREIGN KEY ... REFERENCES target_table
        current_table = None
        for line in schema.splitlines():
            m_table = re.search(r'CREATE\s+TABLE\s+([a-zA-Z0-9_]+)', line, re.IGNORECASE)
            if m_table:
                current_table = m_table.group(1)
                if current_table not in graph:
                    graph[current_table] = set()
            elif current_table:
                m_ref = re.search(r'REFERENCES\s+([a-zA-Z0-9_]+)', line, re.IGNORECASE)
                if m_ref:
                    ref_table = m_ref.group(1)
                    graph[current_table].add(ref_table)
                    if ref_table not in graph:
                        graph[ref_table] = set()
                    graph[ref_table].add(current_table)

        return graph

    def compute_relational_closure(self, selected_tables: Set[str], graph: Dict[str, Set[str]]) -> Set[str]:
        """
        Relational Closure:
        Given candidate selected tables and the foreign key relationship graph,
        computes shortest paths between selected tables to connect disconnected tables
        and return the closed set of tables.
        """
        valid_selected = {t for t in selected_tables if t in graph}
        if not valid_selected:
            return selected_tables

        if len(valid_selected) <= 1:
            return valid_selected

        closure = set(valid_selected)

        # BFS shortest path between pairs of selected tables
        def bfs_shortest_path(start: str, target: str) -> List[str]:
            if start == target:
                return [start]
            queue = deque([[start]])
            visited = {start}
            while queue:
                path = queue.popleft()
                node = path[-1]
                for neighbor in graph.get(node, []):
                    if neighbor == target:
                        return path + [neighbor]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(path + [neighbor])
            return []

        table_list = list(valid_selected)
        for i in range(len(table_list)):
            for j in range(i + 1, len(table_list)):
                t1, t2 = table_list[i], table_list[j]
                path = bfs_shortest_path(t1, t2)
                if path:
                    closure.update(path)

        return closure

    def _call_openai(self, prompt: str) -> str:
        return call_openai_with_retry(self.client, self.model_name, prompt)

    def _direct_link(self, question: str, schema: str, values: Dict[str, List[str]]) -> Set[str]:
        prompt = PROMPT_DIRECT_LINKING.format(
            schema=schema,
            question=question,
            values=str(values)
        )
        response = self._call_openai(prompt)
        return self._parse_tables(response)

    def _reversed_link(self, question: str, schema: str, values: Dict[str, List[str]]) -> Set[str]:
        prompt = PROMPT_GENERATE_SKELETON.format(
            schema=schema,
            question=question
        )
        response = self._call_openai(prompt)
        try:
            parsed = sqlglot.parse_one(response)
            tables = set()
            for table in parsed.find_all(sqlglot.exp.Table):
                tables.add(table.name)
            return tables
        except:
            return set()

    def _value_based_link(self, values: Dict[str, List[str]]) -> Set[str]:
        tables = set()
        for key in values.keys():
            table_name = key.split('.')[0]
            tables.add(table_name)
        return tables

    def _parse_tables(self, text: str) -> Set[str]:
        tables = set()
        matches = re.findall(r'\b([a-zA-Z0-9_]+)(?:\.[a-zA-Z0-9_]+)?\b', text)
        for m in matches:
            tables.add(m)
        return tables

    def _filter_schema_str(self, full_schema: str, relevant_tables: Set[str]) -> str:
        if not relevant_tables:
            return full_schema
            
        blocks = full_schema.strip().split("CREATE TABLE")
        filtered_blocks = []
        for block in blocks:
            if not block.strip():
                continue
            lines = block.strip().splitlines()
            header = lines[0].strip()
            table_name_match = re.match(r'^([a-zA-Z0-9_]+)', header)
            if table_name_match:
                tbl_name = table_name_match.group(1)
                if tbl_name in relevant_tables:
                    filtered_blocks.append("CREATE TABLE " + block.strip())

        if not filtered_blocks:
            return full_schema
            
        return "\n\n".join(filtered_blocks) + "\n"
