"""Read the messages sent through the Contact page.

Messages are stored in the database and there is no automatic email, so this is how
the operator reads them.

    python scripts/list_contact_messages.py              # unhandled messages, newest first
    python scripts/list_contact_messages.py --all        # include handled ones
    python scripts/list_contact_messages.py --done 12    # mark message 12 handled
    python scripts/list_contact_messages.py --delete 12  # delete message 12 (for a privacy request)

Stop the backend before marking or deleting: SQLite allows one writer at a time.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database.session import SessionLocal  # noqa: E402
from app.models.contact_message import ContactMessage  # noqa: E402
from app.services.contact_service import TOPICS, ensure_table  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--all", action="store_true", help="include handled messages")
    parser.add_argument("--done", type=int, metavar="ID", help="mark a message handled")
    parser.add_argument("--delete", type=int, metavar="ID", help="delete a message")
    args = parser.parse_args()

    with SessionLocal() as session:
        ensure_table(session)

        for action, target in (("done", args.done), ("delete", args.delete)):
            if target is None:
                continue
            message = session.get(ContactMessage, target)
            if message is None:
                print(f"No message with id {target}.")
                return 1
            if action == "done":
                message.handled = True
                print(f"Message {target} marked handled.")
            else:
                session.delete(message)
                print(f"Message {target} deleted.")
            session.commit()
            return 0

        query = session.query(ContactMessage).order_by(ContactMessage.created_at.desc())
        if not args.all:
            query = query.filter(ContactMessage.handled.is_(False))
        messages = query.all()
        if not messages:
            print("No unhandled messages." if not args.all else "No messages.")
            return 0
        for m in messages:
            who = f"{m.name} <{m.email}>" if m.name else m.email
            print(f"\n#{m.id}  {m.created_at:%Y-%m-%d %H:%M}  [{TOPICS.get(m.topic, m.topic)}]")
            print(f"from: {who}")
            print(m.message)
        print(f"\n{len(messages)} message(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
