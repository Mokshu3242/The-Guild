from sqlmodel import Session, create_engine

from app.config import settings

engine = create_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)


def get_session():
    with Session(engine) as session:
        yield session