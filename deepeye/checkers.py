from typing import List, Tuple
from openai import OpenAI
from typing import List, Tuple
from openai import OpenAI
from .utils import PROMPT_REVISE_SQL, call_openai_with_retry
import sqlglot
import re

class Checker:
    def check(self, sql: str) -> Tuple[bool, str]:
        """Returns (is_valid, error_message)"""
        raise NotImplementedError

class SyntaxChecker(Checker):
    def check(self, sql: str) -> Tuple[bool, str]:
        try:
            sqlglot.transpile(sql, read="sqlite", write="sqlite")
            return True, ""
        except Exception as e:
            return False, f"Syntax Error: {str(e)}"

class JoinChecker(Checker):
    def check(self, sql: str) -> Tuple[bool, str]:
        # Basic check: if JOIN is used, ON must be used
        if "JOIN" in sql.upper() and "ON" not in sql.upper():
            return False, "JOIN clause missing ON condition."
        return True, ""

class ToolChain:
    def __init__(self, client: OpenAI, model_name: str):
        self.client = client
        self.model_name = model_name
        self.checkers = [
            SyntaxChecker(),
            JoinChecker()
        ]

    def run(self, sql: str, question: str, schema: str) -> str:
        current_sql = sql
        
        for checker in self.checkers:
            is_valid, error = checker.check(current_sql)
            if not is_valid:
                print(f"Checker found error: {error}. Revising...")
                current_sql = self._revise(current_sql, question, error)
        
        return current_sql

    def _revise(self, sql: str, question: str, error: str) -> str:
        prompt = PROMPT_REVISE_SQL.format(
            question=question,
            sql=sql,
            error=error
        )
        
        revised = call_openai_with_retry(self.client, self.model_name, prompt)
        return revised.replace("```sql", "").replace("```", "").strip()
