import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

def print_table_info(table_name):
    cur.execute(f"""
        SELECT column_name, data_type, column_default, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = '{table_name}'
        ORDER BY ordinal_position
    """)
    print(f"{table_name} columns:")
    for row in cur.fetchall():
        print(" ", row)

print_table_info('students')
print_table_info('invites')

cur.close()
conn.close()
