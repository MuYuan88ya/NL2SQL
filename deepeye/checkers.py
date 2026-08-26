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

class SelectChecker(Checker):
    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        try:
            parsed = sqlglot.parse_one(sql, read="sqlite")
            for select in parsed.find_all(sqlglot.exp.Select):
                for expr in select.expressions:
                    if isinstance(expr, sqlglot.exp.Star):
                        return False, "SELECT Check Warning: 'SELECT *' detected. Please project only the specific column(s) requested by the user question."
                    if isinstance(expr, sqlglot.exp.Column) and isinstance(expr.this, sqlglot.exp.Star):
                        return False, "SELECT Check Warning: 'SELECT table.*' detected. Please project only the specific column(s) requested by the user question."
            return True, ""
        except Exception:
            if re.search(r'\bSELECT\s+\*\s+FROM\b', sql, re.IGNORECASE):
                return False, "SELECT Check Warning: 'SELECT *' detected. Please project only the specific column(s) requested by the user question."
            return True, ""

class NullChecker(Checker):
    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        # 1. Check for '= NULL' or '!= NULL' or '<> NULL'
        if re.search(r'(?:=|\!=|<>)\s*NULL\b', sql, re.IGNORECASE):
            return False, "NULL Trap Warning: Invalid NULL comparison using '=' or '!='. Use 'IS NULL' or 'IS NOT NULL' instead."

        # 2. Check for 'NOT IN (SELECT ...)' which can fail when NULL values exist in subquery
        if re.search(r'\bNOT\s+IN\s*\(\s*SELECT\b', sql, re.IGNORECASE):
            return False, "NULL Trap Warning: 'NOT IN (SELECT ...)' subquery detected. If the subquery column contains NULLs, the condition evaluates to UNKNOWN. Consider using 'NOT EXISTS' instead."

        return True, ""

class TimeChecker(Checker):
    NON_SQLITE_TIME_FUNCS = ["YEAR", "MONTH", "DAY", "HOUR", "MINUTE", "SECOND", "NOW", "CURDATE", "CURTIME", "DATEDIFF", "DATE_ADD", "DATE_SUB", "TIMEDIFF"]

    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        try:
            parsed = sqlglot.parse_one(sql, read="sqlite")
            for func in parsed.find_all(sqlglot.exp.Anonymous, sqlglot.exp.Func):
                func_name = func.name.upper() if hasattr(func, "name") else ""
                if func_name in self.NON_SQLITE_TIME_FUNCS:
                    return False, f"Time Function Warning: SQLite does not support function '{func_name}()'. Use SQLite functions like strftime('%Y', column) or date('now') instead."
        except Exception:
            pass

        for func in self.NON_SQLITE_TIME_FUNCS:
            pattern = rf'\b{func}\s*\('
            if re.search(pattern, sql, re.IGNORECASE):
                return False, f"Time Function Warning: SQLite does not support function '{func}()'. Use SQLite functions like strftime('%Y', column) or date('now') instead."

        return True, ""

class OrderByChecker(Checker):
    def check(self, sql: str, db_path: str = None) -> Tuple[bool, str]:
        try:
            parsed = sqlglot.parse_one(sql, read="sqlite")
            for order in parsed.find_all(sqlglot.exp.Order):
                for ordered in order.expressions:
                    if not ordered.this:
                        return False, "ORDER BY Warning: Invalid ORDER BY clause."
            if re.search(r'\bORDER\s+BY\s*(?:LIMIT|WHERE|GROUP|;|$)', sql, re.IGNORECASE):
                return False, "ORDER BY Warning: Empty ORDER BY clause detected."
        except Exception:
            if re.search(r'\bORDER\s+BY\s*(?:LIMIT|WHERE|GROUP|;|$)', sql, re.IGNORECASE):
                return False, "ORDER BY Warning: Empty ORDER BY clause detected."

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
            SelectChecker(),
            NullChecker(),
            TimeChecker(),
            OrderByChecker(),
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
