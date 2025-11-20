from typing import List, Dict, Set
from openai import OpenAI
from typing import List, Dict, Set
from openai import OpenAI
from .utils import PROMPT_DIRECT_LINKING, PROMPT_GENERATE_SKELETON, call_openai_with_retry
import sqlglot

class SchemaLinker:
    def __init__(self, client: OpenAI, model_name: str):
        self.client = client
        self.model_name = model_name

    def link(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        """Combines Direct, Reversed, and Value-based linking."""
        
        # 1. Direct Linking
        direct_schema = self._direct_link(question, schema, values)
        
        # 2. Reversed Linking
        reversed_schema = self._reversed_link(question, schema, values)
        
        # 3. Value-based Linking
        value_schema = self._value_based_link(values)
        
        # Union
        all_tables = direct_schema.union(reversed_schema).union(value_schema)
        
        # Filter schema string to only include relevant tables (Simplified for MVP)
        # In a real system, we would parse the full schema and reconstruct it.
        # Here we just return the full schema if we can't easily filter, 
        # OR we try to filter lines.
        
        # For MVP, let's just return the full schema but append a note about focused tables
        # to the prompt context if we were passing this downstream.
        # But the paper says "Linked Schema" is passed.
        # Let's try to filter the schema string.
        
        filtered_schema = self._filter_schema_str(schema, all_tables)
        return filtered_schema

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
        # Use skeleton generation as a proxy for "draft SQL" for reversed linking
        # The paper says "Generate a draft SQL query directly... then use a static parser"
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
        # Simple heuristic parser
        tables = set()
        # Assuming format Table.Column or just Table
        import re
        matches = re.findall(r'\b([a-zA-Z0-9_]+)(?:\.[a-zA-Z0-9_]+)?\b', text)
        for m in matches:
            tables.add(m)
        return tables

    def _filter_schema_str(self, full_schema: str, relevant_tables: Set[str]) -> str:
        # Simple line-based filter
        lines = full_schema.split('\n')
        filtered = []
        keep = False
        for line in lines:
            if line.strip().startswith("CREATE TABLE"):
                table_name = line.split()[2]
                if table_name in relevant_tables:
                    keep = True
                else:
                    keep = False
            
            if keep:
                filtered.append(line)
                
        if not filtered:
            return full_schema # Fallback
            
        return "\n".join(filtered)
