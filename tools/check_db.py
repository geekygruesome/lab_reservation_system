import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE_DIR, 'data', 'lab_reservations.db')

def main():
    abs_path = os.path.abspath(DB)
    print('ABS_PATH:', abs_path)
    exists = os.path.exists(DB)
    print('EXISTS:', exists)
    if not exists:
        print('Database file not found.')
        return
    try:
        conn = sqlite3.connect(DB)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
        print('TABLES:', tables)
        conn.close()
    except sqlite3.DatabaseError as e:
        print('SQLITE ERROR:', e)

if __name__ == '__main__':
    main()
