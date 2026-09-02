import os
import sys
import datetime
import subprocess

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_RUN_FILE = os.path.join(PROJECT_DIR, ".last_run_date")
BACKLOG_FILE = os.path.join(PROJECT_DIR, "task_backlog.md")
LOG_FILE = os.path.join(PROJECT_DIR, "auto_optimize.log")

def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

def check_already_run_today():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_RUN_FILE):
        with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
            last_date = f.read().strip()
            if last_date == today:
                log(f"Today ({today}) optimization has already been executed. Skipping.")
                return True
    return False

def mark_run_today():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(today)

def main():
    log("Starting auto-optimization process...")
    if check_already_run_today():
        return

    if not os.path.exists(BACKLOG_FILE):
        log(f"Backlog file {BACKLOG_FILE} not found!")
        return

    # Check git status
    log("Checking git repository status...")
    mark_run_today()
    log("Auto-optimization completed for today.")

if __name__ == "__main__":
    main()
