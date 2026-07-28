import os
import sys
import uuid

# Ensure we can import from current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

import auth
from database import SessionLocal, Profile, ensure_tables

def create_initial_admin():
    email = "superadmin99@example.com"
    password = "password123!"
    full_name = "Super Admin"

    print("Ensuring tables exist...")
    ensure_tables()

    print(f"Creating user {email} in Supabase Auth...")
    res = auth.supabase_admin_create_user(email, password, full_name)
    print(f"Create user response: {res}")
    
    if res.get("error"):
        print(f"Error creating auth user: {res.get('msg') or res.get('error')}")
        if "already registered" not in str(res).lower():
            return
            
    # Assuming user exists or was just created, we need their ID.
    # To get ID, we can just sign in.
    print("Signing in to get user ID...")
    login_res = auth.supabase_sign_in(email, password)
    user_id = login_res.get("user", {}).get("id")
    
    if not user_id:
        print(f"Failed to sign in: {login_res}")
        return
        
    print(f"User ID is {user_id}. Creating profile in database...")
    
    db = SessionLocal()
    try:
        uid = uuid.UUID(user_id)
        profile = db.query(Profile).filter(Profile.id == uid).first()
        if not profile:
            profile = Profile(
                id=uid,
                email=email,
                full_name=full_name,
                role="admin"
            )
            db.add(profile)
            db.commit()
            print("Profile created successfully!")
        else:
            print("Profile already exists!")
    finally:
        db.close()

if __name__ == "__main__":
    create_initial_admin()
