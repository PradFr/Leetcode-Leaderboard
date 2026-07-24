import os
from dotenv import load_dotenv
import httpx

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

email = input("Enter the email to test resend on: ").strip()

url = f"{SUPABASE_URL}/auth/v1/resend"
payload = {"type": "signup", "email": email}
headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}

print(f"\nPOST {url}")
print(f"Payload: {payload}")
r = httpx.post(url, json=payload, headers=headers, timeout=15)
print(f"Status: {r.status_code}")
print(f"Response: {r.text}")
