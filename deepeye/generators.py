import math
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .utils import PROMPT_GENERATE_SKELETON, PROMPT_FILL_SKELETON, PROMPT_ICL_GEN, PROMPT_DNC_GEN, call_openai_with_retry

DEFAULT_GOLD_EXAMPLES = [
    {
        "question": "How many students are enrolled in total?",
        "sql": "SELECT COUNT(*) FROM students;",
        "tables": ["students"]
    },
    {
        "question": "List all courses offered by the Computer Science department.",
        "sql": "SELECT course_name FROM courses WHERE department = 'Computer Science';",
        "tables": ["courses"]
    },
    {
        "question": "What is the average GPA of students majoring in Mathematics?",
        "sql": "SELECT AVG(gpa) FROM students WHERE major = 'Mathematics';",
        "tables": ["students"]
    },
    {
        "question": "Find the names of students who received an 'A' grade in any course.",
        "sql": "SELECT DISTINCT students.name FROM students JOIN enrollments ON students.student_id = enrollments.student_id WHERE enrollments.grade = 'A';",
        "tables": ["students", "enrollments"]
    },
    {
        "question": "Which course has the highest number of enrolled students?",
        "sql": "SELECT courses.course_name, COUNT(enrollments.student_id) AS student_count FROM courses JOIN enrollments ON courses.course_id = enrollments.course_id GROUP BY courses.course_id ORDER BY student_count DESC LIMIT 1;",
        "tables": ["courses", "enrollments"]
    },
    {
        "question": "Show the student name and age for students older than 20 with GPA above 3.5.",
        "sql": "SELECT name, age FROM students WHERE age > 20 AND gpa > 3.5;",
        "tables": ["students"]
    },
    {
        "question": "List the course names and credits for courses with more than 3 credits.",
        "sql": "SELECT course_name, credits FROM courses WHERE credits > 3;",
        "tables": ["courses"]
    },
    {
        "question": "Find students who are not enrolled in any course.",
        "sql": "SELECT name FROM students WHERE student_id NOT IN (SELECT student_id FROM enrollments);",
        "tables": ["students", "enrollments"]
    }
]

STOP_WORDS = {"what", "is", "the", "of", "a", "an", "in", "on", "for", "to", "are", "by", "how", "many", "which", "show", "list", "find", "all"}

class DynamicICLRetriever:
    """
    Dynamic In-Context Learning (DAIL-SQL paradigm) Example Retriever.
    Dynamically selects top-k few-shot demonstrations based on query similarity.
    """
    def __init__(self, examples: Optional[List[Dict[str, Any]]] = None, client: Optional[OpenAI] = None):
        self.examples = examples or DEFAULT_GOLD_EXAMPLES
        self.client = client

    def _compute_similarity(self, q1: str, q2: str) -> float:
        words1 = set(re.findall(r'\b\w+\b', q1.lower()))
        words2 = set(re.findall(r'\b\w+\b', q2.lower()))
        if not words1 or not words2:
            return 0.0

        content1 = {w for w in words1 if w not in STOP_WORDS}
        content2 = {w for w in words2 if w not in STOP_WORDS}

        content_score = 0.0
        if content1 and content2:
            intersection = len(content1.intersection(content2))
            union = len(content1.union(content2))
            content_score = intersection / union if union > 0 else 0.0

        raw_intersect = len(words1.intersection(words2))
        raw_union = len(words1.union(words2))
        raw_score = raw_intersect / raw_union if raw_union > 0 else 0.0

        return 0.8 * content_score + 0.2 * raw_score

    def retrieve(self, question: str, k: int = 3) -> str:
        scored = []
        for eg in self.examples:
            score = self._compute_similarity(question, eg["question"])
            scored.append((eg, score))
            
        scored.sort(key=lambda x: x[1], reverse=True)
        top_examples = [item[0] for item in scored[:k]]
        
        formatted = []
        for eg in top_examples:
            formatted.append(f"Q: {eg['question']}\nSQL: {eg['sql']}")
            
        return "\n\n".join(formatted)

class SQLGenerator:
    def __init__(self, client: OpenAI, model_name: str):
        self.client = client
        self.model_name = model_name

    def generate(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        raise NotImplementedError

    def _call_openai(self, prompt: str) -> str:
        return call_openai_with_retry(self.client, self.model_name, prompt)

    def _clean_sql(self, sql: str) -> str:
        return sql.replace("```sql", "").replace("```", "").strip()

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

class ICLGenerator(SQLGenerator):
    def __init__(self, client: OpenAI, model_name: str, examples: Optional[List[Dict[str, Any]]] = None):
        super().__init__(client, model_name)
        self.retriever = DynamicICLRetriever(examples=examples, client=client)

    def generate(self, question: str, schema: str, values: Dict[str, List[str]], k: int = 3) -> str:
        examples_str = self.retriever.retrieve(question, k=k)
        
        prompt = PROMPT_ICL_GEN.format(
            schema=schema,
            examples=examples_str,
            question=question,
            values=str(values)
        )
        sql = self._call_openai(prompt)
        return self._clean_sql(sql)

class DivideAndConquerGenerator(SQLGenerator):
    def generate(self, question: str, schema: str, values: Dict[str, List[str]]) -> str:
        prompt = PROMPT_DNC_GEN.format(
            schema=schema,
            question=question,
            values=str(values)
        )
        sql = self._call_openai(prompt)
        return self._clean_sql(sql)
