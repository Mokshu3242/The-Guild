"""Add the read-only judge account (14A) to the demo guild, without a reset.

1. Supabase > Authentication > Users > Add user:
   email judge@guild.test, the password from the /try page, tick "Auto confirm".
2. From the backend folder:  python -m scripts.add_judge
Safe to run again.
"""
from dotenv import load_dotenv

load_dotenv()

from sqlmodel import Session, select  # noqa: E402

from app.db import engine  # noqa: E402
from app.models import Guild, Member  # noqa: E402
from scripts.reset_demo import JUDGE, supabase_user_id  # noqa: E402


def add_judge(session: Session, guild: Guild) -> Member | None:
    user_id = supabase_user_id(session, JUDGE["email"], required=False)
    if not user_id:
        return None
    m = session.exec(select(Member).where(Member.user_id == user_id)).first()
    if m:
        m.guild_id, m.role, m.read_only, m.available = guild.id, "admin", True, False
    else:
        m = Member(guild_id=guild.id, user_id=user_id, name=JUDGE["name"], email=JUDGE["email"],
                   role="admin", read_only=True, available=False, skills=[])
    session.add(m)
    return m


if __name__ == "__main__":
    with Session(engine) as session:
        guild = session.exec(select(Guild).where(Guild.name == "Design Collective")).first() \
            or session.exec(select(Guild)).first()
        m = add_judge(session, guild)
        if not m:
            raise SystemExit(f"No Supabase login for {JUDGE['email']}. Create it in Authentication > Users first.")
        session.commit()
        print(f"{m.name} ({m.email}) is a read-only admin in {guild.name}.")
