import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from dotenv import load_dotenv

# resolve .env relative to the project root (one level above alembic/)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── database URL ─────────────────────────────────────────────────────────────
_url = os.getenv("DATABASE_URL")
if not _url:
    raise RuntimeError("DATABASE_URL is not set — add it to your .env file.")

config.set_main_option("sqlalchemy.url", _url)

# ── target metadata ───────────────────────────────────────────────────────────
# When models exist, replace None with your Base.metadata, e.g.:
#
#   from app.models import Base
#   target_metadata = Base.metadata
#
target_metadata = None


# ── offline mode — generates SQL without a live connection ────────────────────
def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── online mode — runs against a live async connection ────────────────────────
def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
