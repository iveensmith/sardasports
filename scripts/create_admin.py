"""Create an administrator account, or promote an existing member to administrator.

    python -m scripts.create_admin you@example.com

If the address has no account, one is created (you are asked for a password; it is not echoed and
not stored anywhere but as a hash). If it has, that account is made an administrator. In both
cases the e-mail is marked as confirmed, because the person at the keyboard is the owner.

Run it where the database is: on the server, inside the api container:

    docker compose ... exec api python -m scripts.create_admin you@example.com
"""

from __future__ import annotations

import getpass
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app.models  # noqa: E402,F401
from app.database.session import SessionLocal  # noqa: E402
from app.models.account import ROLE_ADMIN, AuditLog, User  # noqa: E402
from app.services import auth_service  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 2
    try:
        email = auth_service.validate_email(args[0])
    except auth_service.AuthError as error:
        print(error.message)
        return 2

    now = datetime.now(UTC).replace(tzinfo=None)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            password = getpass.getpass("Choose a password (10+ characters): ")
            again = getpass.getpass("Type it again: ")
            if password != again:
                print("The two passwords did not match.")
                return 1
            try:
                auth_service.validate_password(password, email)
            except auth_service.AuthError as error:
                print(error.message)
                return 1
            user = User(
                email=email,
                password_hash=auth_service.hash_password(password),
                role=ROLE_ADMIN,
                email_verified_at=now,
                over_18_confirmed_at=now,
                terms_accepted_version=auth_service.TERMS_VERSION,
            )
            db.add(user)
            action = "admin.created"
        else:
            user.role = ROLE_ADMIN
            if user.email_verified_at is None:
                user.email_verified_at = now
            action = "admin.promoted"
        db.flush()
        db.add(AuditLog(actor_id=None, action=action, target=f"user:{user.id}"))
        db.commit()
        print(f"{email} is now an administrator.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
