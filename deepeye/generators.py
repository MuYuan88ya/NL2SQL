from typing import List, Dict
from openai import OpenAI
from openai import OpenAI
from .utils import PROMPT_GENERATE_SKELETON, PROMPT_FILL_SKELETON, PROMPT_ICL_GEN, PROMPT_DNC_GEN, call_openai_with_retry

class SQLGenerator:
    def __init__(self, client: OpenAI, model_name: str):
        self.client = client
        self.model_name = model_name

    def generate(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        raise NotImplementedError

    def _call_openai(self, prompt: str) -> str:
        return call_openai_with_retry(self.client, self.model_name, prompt)

class SkeletonGenerator(SQLGenerator):
    def generate(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        # 1. Generate Skeleton
        skel_prompt = PROMPT_GENERATE_SKELETON.format(schema=schema, question=question)
        skeleton = self._call_openai(skel_prompt)
        
        # 2. Fill Skeleton
        fill_prompt = PROMPT_FILL_SKELETON.format(
            skeleton=skeleton,
            question=question,
            values=str(values)
        )
        sql = self._call_openai(fill_prompt)
        
        return self._clean_sql(sql)

    def _clean_sql(self, sql: str) -> str:
        return sql.replace("```sql", "").replace("```", "").strip()

class ICLGenerator(SQLGenerator):
    def generate(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        # Hardcoded examples for MVP
        examples = """
        Q: How many students are there?
        SQL: SELECT COUNT(*) FROM students;
        
        Q: List all courses in Computer Science.
        SQL: SELECT course_name FROM courses WHERE department = 'Computer Science';
        """
        
        prompt = PROMPT_ICL_GEN.format(
            schema=schema,
            examples=examples,
            question=question,
            values=str(values)
        )
        sql = self._call_openai(prompt)
        
        return self._clean_sql(sql)

    def _clean_sql(self, sql: str) -> str:
        return sql.replace("```sql", "").replace("```", "").strip()

class DivideAndConquerGenerator(SQLGenerator):
    def generate(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        # Simplified D&C: Just ask LLM to break it down internally
        prompt = PROMPT_DNC_GEN.format(
            schema=schema,
            question=question,
            values=str(values)
        )
        sql = self._call_openai(prompt)
        
        return self._clean_sql(sql)

    def _clean_sql(self, sql: str) -> str:
        return sql.replace("```sql", "").replace("```", "").strip()
