import os
import sys
import argparse
from tabulate import tabulate
from deepeye.core import DeepEyeSQL
from deepeye.utils import execute_sql_with_headers, get_schema_info

def interactive_session(pipeline: DeepEyeSQL, execute_result: bool = True):
    print("\n" + "="*60)
    print("🤖 DeepEye-SQL 交互式控制台 (Interactive REPL)")
    print("💡 直接输入自然语言问题即可生成 SQL，输入 'exit' 或 'quit' 退出。")
    print("="*60)
    
    while True:
        try:
            question = input("\n📝 请输入查询问题 > ").strip()
            if not question:
                continue
            if question.lower() in ("exit", "quit", "q"):
                print("👋 已退出交互会话。")
                break
                
            sql = pipeline.run(question)
            print("\n" + "-"*50)
            print(f"✨ 生成的 SQL:\n{sql}")
            print("-"*50)
            
            if execute_result:
                headers, rows = execute_sql_with_headers(pipeline.db_path, sql)
                print("\n📊 查询执行结果:")
                if rows and not (len(rows) == 1 and headers == ["Error"]):
                    print(tabulate(rows, headers=headers, tablefmt="rounded_grid"))
                elif headers == ["Error"]:
                    print(f"❌ 执行错误: {rows[0][0]}")
                else:
                    print("(返回 0 行结果)")
        except (KeyboardInterrupt, EOFError):
            print("\n👋 已退出交互会话。")
            break
        except Exception as e:
            print(f"❌ 运行出错: {e}")

def main():
    parser = argparse.ArgumentParser(description="DeepEye-SQL: Multi-stage Agent Pipeline for Natural Language to SQL")
    default_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "school.db")
    parser.add_argument("--db", type=str, default=default_db, help="Path to SQLite database")
    parser.add_argument("--question", "-q", type=str, default="Show me all students", help="Natural language question")
    parser.add_argument("--execute", "-e", action="store_true", help="Execute generated SQL and display results in a table")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive multi-turn shell")
    parser.add_argument("--schema", "-s", action="store_true", help="Print database schema and exit")
    parser.add_argument("--api_key", type=str, required=False, help="OpenAI API Key")
    parser.add_argument("--base_url", type=str, required=False, help="OpenAI Base URL")
    parser.add_argument("--model_name", type=str, required=False, help="OpenAI Model Name")
    
    args = parser.parse_args()
    
    from dotenv import load_dotenv
    load_dotenv()

    if not os.path.exists(args.db):
        print(f"Error: Database file {args.db} not found. Run 'python create_dummy_db.py' first.")
        return

    if args.schema:
        print("\n" + "="*50)
        print(f"Database Schema ({args.db}):")
        print("="*50)
        print(get_schema_info(args.db))
        return

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    
    if not os.environ.get("OPENAI_API_KEY"):
         print("Error: OpenAI API Key is required. Pass it via --api_key or set OPENAI_API_KEY env var.")
         return

    pipeline = DeepEyeSQL(
        db_path=args.db,
        api_key=args.api_key,
        base_url=args.base_url,
        model_name=args.model_name
    )
    
    if args.interactive:
        interactive_session(pipeline, execute_result=True)
        return

    try:
        sql = pipeline.run(args.question)
        print("\n" + "="*50)
        print(f"FINAL SQL: {sql}")
        print("="*50)
        
        if args.execute:
            headers, rows = execute_sql_with_headers(args.db, sql)
            print("\nExecution Result:")
            if rows and not (len(rows) == 1 and headers == ["Error"]):
                print(tabulate(rows, headers=headers, tablefmt="rounded_grid"))
            elif headers == ["Error"]:
                print(f"Execution Error: {rows[0][0]}")
            else:
                print("(0 rows returned)")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
