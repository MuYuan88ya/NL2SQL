import os
from typing import List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

from .schema_linking import SchemaLinker
from .value_retrieval import ValueRetriever
from .generators import SkeletonGenerator, ICLGenerator, DivideAndConquerGenerator
from .checkers import ToolChain
from .selection import ConfidenceSelector
from .utils import get_schema_info

load_dotenv()

class DeepEyeSQL:
    def __init__(self, db_path: str, api_key: str = None, base_url: str = None, model_name: str = None):
        self.db_path = db_path
        
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model_name = model_name or os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
        
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables.")
            
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.schema = get_schema_info(db_path)
        
        # Initialize components
        self.value_retriever = ValueRetriever(db_path)
        self.schema_linker = SchemaLinker(self.client, self.model_name)
        self.generators = [
            SkeletonGenerator(self.client, self.model_name),
            ICLGenerator(self.client, self.model_name),
            DivideAndConquerGenerator(self.client, self.model_name)
        ]
        self.checker_chain = ToolChain(self.client, self.model_name)
        self.selector = ConfidenceSelector(self.client, self.model_name, db_path)

    def run(self, question: str) -> str:
        print(f"Processing question: {question}")
        
        # Phase 1: Intent Scoping & Semantic Grounding
        print("Phase 1: Intent Scoping...")
        values = self.value_retriever.retrieve(question)
        linked_schema = self.schema_linker.link(question, self.schema, values)
        print(f"Linked Schema (partial): {linked_schema[:100]}...")
        
        # Phase 2: N-version Generation
        print("Phase 2: N-version Generation...")
        candidates = []
        for gen in self.generators:
            try:
                sql = gen.generate(question, linked_schema, values)
                candidates.append(sql)
                print(f"Generated SQL: {sql}")
            except Exception as e:
                print(f"Generation failed: {e}")
            
        # Phase 3: Unit Testing & Revision
        print("Phase 3: Unit Testing & Revision...")
        revised_candidates = []
        for sql in candidates:
            revised_sql = self.checker_chain.run(sql, question, linked_schema)
            revised_candidates.append(revised_sql)
            print(f"Revised SQL: {revised_sql}")
            
        # Phase 4: Selection
        print("Phase 4: Selection...")
        final_sql = self.selector.select(revised_candidates, question)
        print(f"Final Selected SQL: {final_sql}")
        
        return final_sql
