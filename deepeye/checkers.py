import os
import re
import sqlglot
from typing import List, Tuple, Any
from openai import OpenAI
from .utils import PROMPT_REVISE_SQL, call_openai_with_retry, execute_sql

class Checker:
    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        """Returns (is_valid, error_message)"""
        raise NotImplementedError

class SyntaxChecker(Checker):
    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        try:
            sqlglot.transpile(sql, read="sqlite", write="sqlite")
            return True, ""
        except Exception as e:
            return False, f"Syntax Error: {str(e)}"

class JoinChecker(Checker):
    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        # Basic check: if JOIN is used, ON must be used
        if "JOIN" in sql.upper() and "ON" not in sql.upper():
            return False, "JOIN clause missing ON condition."
        return True, ""

class ResultChecker(Checker):
    def __init__(self, db_path: str = None):
        self.db_path = db_path

    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        target_db = db_path or self.db_path
        if not target_db or not os.path.exists(target_db):
            return True, ""

        results = execute_sql(target_db, sql)

        # 1. Execution Error check
        if results and isinstance(results[0], str) and results[0].startswith("Error:"):
            return False, f"SQL Execution Error: {results[0]}"

        # 2. Empty Result Set check
        if len(results) == 0:
            return False, "SQL Execution Warning: Query returned an empty result set (0 rows). Verify filter conditions or string literals."

        # 3. All NULL Result Set check
        all_null = True
        for row in results:
            if isinstance(row, tuple):
                if any(val is not None for val in row):
                    all_null = False
                    break
            elif row is not None:
                all_null = False
                break

        if len(results) > 0 and all_null:
            return False, "SQL Execution Warning: Query returned rows containing all NULL values."

        return True, ""

class ToolChain:
    def __init__(self, client: OpenAI, model_name: str, db_path: str = None):
        self.client = client
        self.model_name = model_name
        self.db_path = db_path
        self.checkers = [
            SyntaxChecker(),
            JoinChecker(),
            ResultChecker(db_path=self.db_path)
        ]

    def run(self, sql: str, question: str, schema: str, db_path: str = None) -> str:
        current_sql = sql
        target_db = db_path or self.db_path

        for checker in self.checkers:
            is_valid, error = checker.check(current_sql, db_path=target_db)
            if not is_valid:
                print(f"Checker [{checker.__class__.__name__}] found issue: {error}. Revising...")
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
