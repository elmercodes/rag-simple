# backend/app/migrations.py
from sqlalchemy import inspect, text

from .db import Base, engine
from . import models  # noqa: F401 - ensure models are registered


# ---- Migration helpers ----
DEFAULT_LOCAL_EXTERNAL_ID = "local"
DEFAULT_LOCAL_EMAIL = "local@local"


def _ensure_tables_exist():
    Base.metadata.create_all(bind=engine)


def _ensure_meta_column():
    """
    Lightweight migration to add messages.meta JSON column if missing.
    Safe to run repeatedly.
    """
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("messages")]
    if "meta" not in columns:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE messages ADD COLUMN meta JSON"))
            conn.commit()


def _ensure_column(table: str, column: str, type_sql: str) -> None:
    """
    Add a column to a table if it does not exist.
    """
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(table)]
    if column in columns:
        return
    with engine.connect() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {type_sql}"))
        conn.commit()


def ensure_default_user() -> int:
    """
    Ensure a local fallback user exists for non-auth flows.
    Returns its id.
    """
    with engine.begin() as conn:
        existing = conn.execute(
            text(
                """
                SELECT id FROM users
                WHERE external_id = :ext OR email = :email
                LIMIT 1
                """
            ),
            {"ext": DEFAULT_LOCAL_EXTERNAL_ID, "email": DEFAULT_LOCAL_EMAIL},
        ).fetchone()
        if existing:
            return existing[0]

        result = conn.execute(
            text(
                """
                INSERT INTO users (external_id, email, created_at)
                VALUES (:ext, :email, CURRENT_TIMESTAMP)
                """
            ),
            {"ext": DEFAULT_LOCAL_EXTERNAL_ID, "email": DEFAULT_LOCAL_EMAIL},
        )
        return int(result.lastrowid)


def _conversations_need_rebuild() -> bool:
    with engine.connect() as conn:
        rows = conn.execute(text("PRAGMA table_info(conversations)")).fetchall()
    for row in rows:
        # PRAGMA columns: cid, name, type, notnull, dflt_value, pk
        if row[1] == "user_id":
            return row[3] == 0  # nullable -> rebuild
    # Missing user_id entirely also signals rebuild
    return True


def _rebuild_conversations_table(default_user_id: int) -> None:
    """
    SQLite cannot alter column nullability; rebuild conversations with NOT NULL user_id.
    """
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=off"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS conversations_new (
                    id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    title VARCHAR(255),
                    created_at DATETIME,
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO conversations_new (id, user_id, title, created_at)
                SELECT id, COALESCE(user_id, :default_user_id), title, created_at
                FROM conversations
                """
            ),
            {"default_user_id": default_user_id},
        )

        conn.execute(text("DROP TABLE conversations"))
        conn.execute(text("ALTER TABLE conversations_new RENAME TO conversations"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)"))
        conn.execute(text("PRAGMA foreign_keys=on"))


def _ensure_conversation_index():
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)"
            )
        )


def run_migrations() -> int:
    """
    Apply safe, idempotent migrations and return the default local user id.
    """
    _ensure_tables_exist()
    _ensure_meta_column()
    _ensure_column("documents", "embedding_model", "VARCHAR(255)")
    _ensure_column("documents", "embedding_dim", "INTEGER")
    _ensure_column("documents", "vectorstore_collection", "VARCHAR(255)")
    _ensure_column("document_chunks", "embedding_model", "VARCHAR(255)")
    _ensure_column("document_chunks", "embedding_dim", "INTEGER")
    _ensure_column("document_chunks", "vectorstore_collection", "VARCHAR(255)")
    default_user_id = ensure_default_user()
    if _conversations_need_rebuild():
        _rebuild_conversations_table(default_user_id)
    _ensure_conversation_index()
    return default_user_id
