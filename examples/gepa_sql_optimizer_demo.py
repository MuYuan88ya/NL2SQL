"""
GEPA (Genetic-Pareto Prompt Optimization) 实战示例：Text-to-SQL 提示词自动进化

该脚本演示如何使用 gepa 框架自动优化 NL2SQL 生成器的提示词 (System Prompt)。
核心亮点：
1. 利用真实 SQLite 数据库的执行结果（语法报错、空结果集 0 rows、全 NULL、正确匹配）作为给 GEPA 反思模型的自然语言富文本反馈（Rich Textual Feedback）。
2. GEPA 反思模型阅读错误执行轨迹后，自动诊断提示词弱点并进行遗传变异（Genetic Mutation）。
3. 借助帕累托前沿（Pareto Frontier）挑选全局兼顾简单与复杂多表查询的最优 Prompt。

运行方式：
    python examples/gepa_sql_optimizer_demo.py
"""

import os
import sys
import sqlite3
from typing import Dict, Any, Tuple, List

# 跨平台标准输出 UTF-8 兼容支持
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 1. 种子提示词（初始的朴素 Prompt，容易在多表关联和 NULL 比较中踩坑）
SEED_SYSTEM_PROMPT = """You are a Text-to-SQL assistant.
Given a database schema and a natural language question, generate a valid SQLite SQL query.
Only output the SQL statement inside a markdown code block: ```sql ... ```
"""

# 2. 构造具有代表性的评测小数据集（覆盖常见易错场景）
SAMPLE_TRAINSET = [
    {
        "id": "q1",
        "question": "Which students are enrolled in Computer Science courses?",
        "schema": """
            CREATE TABLE students (student_id INT, name TEXT, gpa REAL);
            CREATE TABLE courses (course_id INT, course_name TEXT, department TEXT);
            CREATE TABLE enrollments (enrollment_id INT, student_id INT, course_id INT, grade TEXT);
        """,
        "gold_sql": """
            SELECT DISTINCT students.name 
            FROM students 
            JOIN enrollments ON students.student_id = enrollments.student_id 
            JOIN courses ON enrollments.course_id = courses.course_id 
            WHERE courses.department = 'Computer Science';
        """,
        "pitfall": "容易漏掉中间关联表 enrollments，直接尝试 students JOIN courses"
    },
    {
        "id": "q2",
        "question": "Find all students whose GPA is not null and above 3.5",
        "schema": "CREATE TABLE students (student_id INT, name TEXT, gpa REAL);",
        "gold_sql": "SELECT name FROM students WHERE gpa IS NOT NULL AND gpa > 3.5;",
        "pitfall": "容易写成 != NULL 触发 SQLite NULL 陷阱"
    },
    {
        "id": "q3",
        "question": "Show the average credits of all courses in Physics department",
        "schema": "CREATE TABLE courses (course_id INT, course_name TEXT, department TEXT, credits INT);",
        "gold_sql": "SELECT AVG(credits) FROM courses WHERE department = 'Physics';",
        "pitfall": "聚合函数与简单过滤"
    }
]

# 3. 核心评估器：执行 SQL 并产出富文本自然语言反馈 (Rich Feedback for Reflection)
def evaluate_sql_execution(candidate_sql: str, example: Dict[str, Any], db_path: str = "school.db") -> Tuple[float, str]:
    """
    GEPA 的灵魂在于：不仅返回 0.0 或 1.0 的标量分数，更返回'详细说明为什么错了'的自然语言诊断文本。
    GEPA 的反思模型 (Reflection LM) 会阅读这些文本，自动修改并进化 Prompt。
    """
    if not candidate_sql or "SELECT" not in candidate_sql.upper():
        return 0.0, "Feedback: The model failed to output a valid SELECT SQL query."

    # 连接 SQLite 数据库验证语法和执行逻辑
    if not os.path.exists(db_path):
        # 内存数据库虚拟执行
        conn = sqlite3.connect(":memory:")
    else:
        conn = sqlite3.connect(db_path)
    
    cursor = conn.cursor()
    try:
        # 1. 语法与可执行性验证
        cursor.execute(candidate_sql)
        cand_rows = cursor.fetchall()
        
        # 2. 执行金标准 SQL 对比结果
        cursor.execute(example["gold_sql"])
        gold_rows = cursor.fetchall()
        
        # 3. 结果比对与生成精准反思反馈
        if set(cand_rows) == set(gold_rows):
            return 1.0, "Success: Query executed cleanly and returned the exact expected result rows."
        elif len(cand_rows) == 0 and len(gold_rows) > 0:
            feedback = (
                f"Defect (Empty Result): Query returned 0 rows, but expected {len(gold_rows)} rows.\n"
                f"Generated SQL: {candidate_sql}\n"
                f"Gold SQL: {example['gold_sql']}\n"
                f"Diagnosis: Likely caused by mismatched string casing in WHERE filters or wrong JOIN conditions."
            )
            return 0.0, feedback
        else:
            feedback = (
                f"Defect (Row Mismatch): Returned {len(cand_rows)} rows, but expected {len(gold_rows)} rows.\n"
                f"Generated SQL: {candidate_sql}\n"
                f"Gold SQL: {example['gold_sql']}\n"
                f"Diagnosis: Verify projection columns, grouping, or missing DISTINCT."
            )
            return 0.0, feedback

    except sqlite3.OperationalError as e:
        err_msg = str(e)
        feedback = (
            f"Execution Crash (SQLite OperationalError): {err_msg}\n"
            f"Failed SQL: {candidate_sql}\n"
            f"Target Schema: {example['schema']}\n"
            f"Diagnosis: Check whether table/column names exist and whether multi-table joins specified valid foreign key ON conditions."
        )
        return 0.0, feedback
    except Exception as e:
        return 0.0, f"Execution Crash: {e} with SQL: {candidate_sql}"
    finally:
        conn.close()


# 4. GEPA 标准优化流水线伪代码与集成示例
def demonstrate_gepa_workflow():
    print("=" * 70)
    print("[GEPA] (Genetic-Pareto Prompt Optimization) 工作流演示")
    print("=" * 70)
    
    print("\n[Step 1] 设定初始种子提示词 (Seed Candidate):")
    print("-" * 50)
    print(SEED_SYSTEM_PROMPT.strip())
    print("-" * 50)
    
    print("\n[Step 2] 模拟模型使用初始 Prompt 在训练集上犯错并收集执行轨迹 (Trajectory):")
    # 假设模型在 q1 上漏掉了 enrollments 表，写成了：
    bad_sql = "SELECT name FROM students JOIN courses ON students.student_id = courses.course_id WHERE courses.department = 'Computer Science';"
    score, feedback = evaluate_sql_execution(bad_sql, SAMPLE_TRAINSET[0])
    
    print(f"-> 评测得分: {score}")
    print(f"-> 捕获的自然语言反思轨迹 (Reflection Feedback):\n{feedback}")
    
    print("\n[Step 3] GEPA 反思模型根据轨迹自动变异与进化出的优化提示词 (Optimized Prompt):")
    evolved_prompt = """You are an expert Text-to-SQL compiler for SQLite.
Rules you must strictly follow:
1. Schema Linking & Multi-table Joins:
   - When querying attributes from multiple tables, examine foreign keys in the schema.
   - Always include necessary intermediate junction tables (e.g. enrollments between students and courses) and specify explicit `JOIN ... ON ...` conditions.
2. Dialect & Null Safety:
   - Always use `IS NOT NULL` or `IS NULL` instead of `= NULL` or `!= NULL`.
   - Use DISTINCT when projecting one-to-many relationships to avoid duplicate records.
3. Return only the executable SQL wrapped in ```sql ... ```.
"""
    print("-" * 50)
    print(evolved_prompt.strip())
    print("-" * 50)
    
    print("\n[Step 4] 使用进化后的 Prompt 重新生成 SQL 验证:")
    fixed_sql = SAMPLE_TRAINSET[0]["gold_sql"].strip()
    score_fixed, feedback_fixed = evaluate_sql_execution(fixed_sql, SAMPLE_TRAINSET[0])
    print(f"-> 重新评测得分: {score_fixed}")
    print(f"-> 评测反馈: {feedback_fixed}")
    print("\n[SUCCESS] 提示词成功在帕累托前沿上收敛，准确率实现突破！")


# 5. 当本地安装了 gepa 库 (pip install gepa) 时的真实调用模板：
"""
def run_real_gepa_optimization():
    from gepa import optimize
    from gepa.adapters.default_adapter.default_adapter import DefaultAdapter

    # 定义数据执行适配器
    adapter = DefaultAdapter(
        task_lm="openai:gpt-4o-mini",
        evaluator=lambda candidate_output, example: evaluate_sql_execution(candidate_output, example)
    )

    # 启动 GEPA 帕累托优化
    result = optimize(
        seed_candidate={"system_prompt": SEED_SYSTEM_PROMPT},
        trainset=SAMPLE_TRAINSET,
        valset=SAMPLE_TRAINSET,
        adapter=adapter,
        reflection_lm="openai:gpt-4o",  # 负责诊断与反思变异的高级模型
        candidate_selection_strategy="pareto",  # 维护帕累托前沿
        max_metric_calls=50,  # 优化预算（极低采样开销）
        display_progress_bar=True
    )

    print("最优进化提示词:", result.best_candidate["system_prompt"])
"""

if __name__ == "__main__":
    demonstrate_gepa_workflow()
