import os
import argparse
import sys
from app.database import SessionLocal, init_db
from app.models.entities import User
from app.services.auth import hash_password

def bootstrap_admin(username: str, email: str, password: str) -> User:
    """Create or update the root administrator account."""
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing:
            existing.hashed_password = hash_password(password)
            existing.role = "admin"
            existing.is_active = True
            db.commit()
            db.refresh(existing)
            print(f"[OK] Administrator '{existing.username}' credentials updated.")
            return existing
        else:
            admin_user = User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                role="admin",
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            print(f"[OK] Administrator '{admin_user.username}' created successfully.")
            return admin_user
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap the initial FuelFlow administrator.")
    parser.add_argument("--username", default=os.getenv("ADMIN_BOOTSTRAP_USERNAME", "admin"), help="Admin username")
    parser.add_argument("--email", default=os.getenv("ADMIN_BOOTSTRAP_EMAIL", "admin@fuelflow.local"), help="Admin email")
    parser.add_argument("--password", default=os.getenv("ADMIN_BOOTSTRAP_PASSWORD"), help="Admin password (min 8 chars)")

    args = parser.parse_args()

    if not args.password:
        print("[ERROR] Please provide --password or set ADMIN_BOOTSTRAP_PASSWORD environment variable.", file=sys.stderr)
        sys.exit(1)

    if len(args.password) < 8:
        print("[ERROR] Password must be at least 8 characters long.", file=sys.stderr)
        sys.exit(1)

    bootstrap_admin(args.username, args.email, args.password)
