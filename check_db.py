import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# Check the id column definition for classes
cur.execute("""
    SELECT column_name, data_type, column_default, is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'classes'
    ORDER BY ordinal_position
""")
print("classes columns:")
for row in cur.fetchall():
    print(" ", row)

# Check sequences
cur.execute("""
    SELECT sequence_name, data_type, start_value, increment
    FROM information_schema.sequences
    WHERE sequence_schema = 'public'
""")
print("\nSequences:")
for row in cur.fetchall():
    print(" ", row)

cur.close()
conn.close()
