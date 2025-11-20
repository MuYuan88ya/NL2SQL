import os
import argparse
from deepeye.core import DeepEyeSQL

def main():
    parser = argparse.ArgumentParser(description="DeepEye-SQL MVP")
    parser.add_argument("--db", type=str, default="g:/NL2SQL/school.db", help="Path to SQLite database")
    parser.add_argument("--question", type=str, default="Show me all students", help="Natural language question")
    parser.add_argument("--api_key", type=str, required=False, help="OpenAI API Key")
    parser.add_argument("--base_url", type=str, required=False, help="OpenAI Base URL")
    parser.add_argument("--model_name", type=str, required=False, help="OpenAI Model Name")
    
    args = parser.parse_args()
    
    # Load env vars if not already loaded (DeepEyeSQL also does it, but good for main check)
    from dotenv import load_dotenv
    load_dotenv()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    
    if not os.environ.get("OPENAI_API_KEY"):
         print("Error: OpenAI API Key is required. Pass it via --api_key or set OPENAI_API_KEY env var.")
         return

    if not os.path.exists(args.db):
        print(f"Error: Database file {args.db} not found. Run create_dummy_db.py first.")
        return

    pipeline = DeepEyeSQL(
        db_path=args.db,
        api_key=args.api_key,
        base_url=args.base_url,
        model_name=args.model_name
    )
    
    try:
        result = pipeline.run(args.question)
        print("\n" + "="*50)
        print(f"FINAL SQL: {result}")
        print("="*50)
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
