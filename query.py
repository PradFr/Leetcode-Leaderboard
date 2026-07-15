from database import SessionLocal
from sqlalchemy import text
db=SessionLocal()
res=db.execute(text("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='students'")).fetchall()
for r in res:
    print(r)
