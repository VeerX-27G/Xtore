from sqlalchemy import create_engine
import os
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL")

if SQLALCHEMY_DATABASE_URL:
    # Heroku may provide either legacy postgres:// or standard postgresql:// URLs.
    if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
    
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
else:
    # Fallback to local SQLite when running on your local machine
    SQLALCHEMY_DATABASE_URL = "sqlite:///./items.db"
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()