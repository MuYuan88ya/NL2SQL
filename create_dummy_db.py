import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "school.db")

def create_dummy_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create Tables
    cursor.execute("""
    CREATE TABLE students (
        student_id INTEGER PRIMARY KEY,
        name TEXT,
        age INTEGER,
        major TEXT,
        gpa REAL
    );
    """)
    
    cursor.execute("""
    CREATE TABLE courses (
        course_id INTEGER PRIMARY KEY,
        course_name TEXT,
        department TEXT,
        credits INTEGER
    );
    """)
    
    cursor.execute("""
    CREATE TABLE enrollments (
        enrollment_id INTEGER PRIMARY KEY,
        student_id INTEGER,
        course_id INTEGER,
        grade TEXT,
        FOREIGN KEY (student_id) REFERENCES students (student_id),
        FOREIGN KEY (course_id) REFERENCES courses (course_id)
    );
    """)
    
    # Insert Data
    students = [
        (1, 'Alice Smith', 20, 'Computer Science', 3.8),
        (2, 'Bob Jones', 21, 'Mathematics', 3.5),
        (3, 'Charlie Brown', 22, 'Physics', 3.2),
        (4, 'David Wilson', 20, 'Computer Science', 3.9),
        (5, 'Eva Davis', 21, 'Biology', 3.6)
    ]
    cursor.executemany("INSERT INTO students VALUES (?, ?, ?, ?, ?)", students)
    
    courses = [
        (101, 'Intro to CS', 'Computer Science', 4),
        (102, 'Calculus I', 'Mathematics', 4),
        (103, 'Physics I', 'Physics', 4),
        (104, 'Data Structures', 'Computer Science', 4),
        (105, 'Organic Chemistry', 'Biology', 4)
    ]
    cursor.executemany("INSERT INTO courses VALUES (?, ?, ?, ?)", courses)
    
    enrollments = [
        (1, 1, 101, 'A'), (2, 1, 102, 'B'),
        (3, 2, 102, 'A'), (4, 2, 103, 'B'),
        (5, 3, 103, 'C'),
        (6, 4, 101, 'A'), (7, 4, 104, 'A'),
        (8, 5, 105, 'A')
    ]
    cursor.executemany("INSERT INTO enrollments VALUES (?, ?, ?, ?)", enrollments)
    
    conn.commit()
    conn.close()
    print(f"Database created at {DB_PATH}")

if __name__ == "__main__":
    create_dummy_db()
