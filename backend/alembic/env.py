"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alembic Environment

Purpose:
    Configures Alembic so it can compare the SQLAlchemy
    models against the live database and generate or apply
    migrations.

Responsibilities:
    - Register every model on Base.metadata.
    - Supply the database URL from application settings.
    - Run migrations in offline or online mode.

How it works:
    Alembic needs two things to work out what changed: the
    schema the code describes, and the schema the database
    currently has. The first comes from Base.metadata, which
    is only populated by importing the models; the second
    from a live connection.

    The database URL is read from app.core.config rather than
    from alembic.ini, so migrations run against the same
    database the application uses and no connection string is
    duplicated, or committed.

Why the models package is imported, not individual models:
    Autogenerate treats a table absent from Base.metadata as
    one that should be DROPPED. If a model is not imported
    before autogenerate inspects the metadata, Alembic will
    quietly write a migration that drops its table, and the
    data with it.

    Importing the package rather than each module means a
    newly added model is registered automatically and cannot
    be forgotten.

Note on migrations as evidence:
    The migration history is the record of how the schema
    reached its present shape, and the dissertation relies on
    it. Migrations are therefore never edited once applied; a
    correction is a new revision. Take a pg_dump before
    running one against a database holding real records.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from app.core.config import get_settings
from app.database.session import Base

# Import the models package rather than individual models.
# Every model must be registered on Base.metadata BEFORE
# autogenerate inspects it, otherwise a table that exists in
# the code is silently treated as one that should be dropped.
# Importing the package guarantees a new model is included.
import app.models  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
