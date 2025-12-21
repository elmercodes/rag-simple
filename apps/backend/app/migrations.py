# backend/app/migrations.py
from sqlalchemy import inspect, text

from .db import Base, engine
from . import models  # noqa: F401 - ensure models are registered


# ---- Migration helpers ----
DEFAULT_LOCAL_EXTERNAL_ID = "local"
DEFAULT_LOCAL_EMAIL = "local@local"


def _table_exists(name: str) -> bool:
    inspector = inspect(engine)
    return name in inspector.get_table_names()


def _column_names(table: str) -> list[str]:
    inspector = inspect(engine)
    return [c["name"] for c in inspector.get_columns(table)]


def _add_column_if_missing(table: str, column: str, type_sql: str) -> None:
    if column in _column_names(table):
        return
    with engine.connect() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {type_sql}"))
        conn.commit()


def _ensure_tables_exist():
    Base.metadata.create_all(bind=engine)


def _ensure_meta_column():
    """
    Lightweight migration to add messages.meta JSON column if missing.
    Safe to run repeatedly.
    """
    if "meta" in _column_names("messages"):
        return
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE messages ADD COLUMN meta JSON"))
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
            return int(existing[0])

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
    if not _table_exists("conversations"):
        return False

    rows = _column_names("conversations")
    if "user_id" not in rows:
        return True

    with engine.connect() as conn:
        schema_rows = conn.execute(text("PRAGMA table_info(conversations)")).fetchall()
    for row in schema_rows:
        if row[1] == "user_id":
            return row[3] == 0  # nullable -> rebuild
    return False


def _rebuild_conversations_table(default_user_id: int) -> None:
    """
    SQLite cannot alter column nullability; rebuild conversations with NOT NULL user_id
    and the newer metadata columns.
    """
    has_focus_type = "focus_type" in _column_names("conversations")
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
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_pinned BOOLEAN DEFAULT 0 NOT NULL,
                    pinned_at DATETIME,
                    pinned_order INTEGER,
                    use_docs_default BOOLEAN DEFAULT 0 NOT NULL,
                    focus_type INTEGER,
                    embedding_model VARCHAR(64),
                    PRIMARY KEY (id),
                    FOREIGN KEY(user_id) REFERENCES users (id)
                )
                """
            )
        )

        focus_select = "focus_type" if has_focus_type else "NULL"
        embedding_select = (
            "embedding_model" if "embedding_model" in _column_names("conversations") else "NULL"
        )
        conn.execute(
            text(
                f"""
                INSERT INTO conversations_new (id, user_id, title, created_at, updated_at, is_pinned, pinned_at, pinned_order, use_docs_default, focus_type, embedding_model)
                SELECT id, COALESCE(user_id, :default_user_id), title, created_at, COALESCE(updated_at, CURRENT_TIMESTAMP), COALESCE(is_pinned, 0), pinned_at, pinned_order, COALESCE(use_docs_default, 0), {focus_select}, {embedding_select}
                FROM conversations
                """
            ),
            {"default_user_id": default_user_id},
        )

        conn.execute(text("DROP TABLE conversations"))
        conn.execute(text("ALTER TABLE conversations_new RENAME TO conversations"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)"))
        conn.execute(text("PRAGMA foreign_keys=on"))


def _ensure_conversation_columns():
    _add_column_if_missing("conversations", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    _add_column_if_missing("conversations", "is_pinned", "BOOLEAN DEFAULT 0")
    _add_column_if_missing("conversations", "pinned_at", "DATETIME")
    _add_column_if_missing("conversations", "pinned_order", "INTEGER")
    _add_column_if_missing("conversations", "use_docs_default", "BOOLEAN DEFAULT 0")
    _add_column_if_missing("conversations", "focus_type", "INTEGER")
    _add_column_if_missing("conversations", "embedding_model", "VARCHAR(64)")


def _ensure_conversation_index():
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_id ON conversations (user_id)"
            )
        )


def _copy_documents_to_attachments():
    """
    One-time migration to move legacy document/ chunk tables to the new attachment naming.
    """
    if not _table_exists("documents"):
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO attachments (
                    id, user_id, conversation_id, name, type, path, file_hash, embedding_model,
                    embedding_dim, vectorstore_collection, created_at
                )
                SELECT
                    id, user_id, conversation_id, filename, mime_type, NULL, file_hash,
                    embedding_model, embedding_dim, vectorstore_collection, created_at
                FROM documents
                """
            )
        )

        if _table_exists("document_chunks"):
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO attachment_chunks (
                        id, user_id, conversation_id, attachment_id, chunk_id, chunk_text, page,
                        chunk_index, section, preview, char_len, embedding_model, embedding_dim,
                        vectorstore_collection, created_at
                    )
                    SELECT
                        id, user_id, conversation_id, document_id, chunk_id, chunk_text, page,
                        chunk_index, section, preview, char_len, embedding_model, embedding_dim,
                        vectorstore_collection, created_at
                    FROM document_chunks
                    """
                )
            )

        conn.execute(text("DROP TABLE IF EXISTS document_chunks"))
        conn.execute(text("DROP TABLE IF EXISTS documents"))


def _ensure_attachment_metadata_columns():
    if _table_exists("attachments"):
        _add_column_if_missing("attachments", "path", "VARCHAR(1024)")
        _add_column_if_missing("attachments", "type", "VARCHAR(50)")
        _add_column_if_missing("attachments", "embedding_model", "VARCHAR(255)")
        _add_column_if_missing("attachments", "embedding_dim", "INTEGER")
        _add_column_if_missing("attachments", "vectorstore_collection", "VARCHAR(255)")
        _add_column_if_missing("attachments", "doc_type", "INTEGER")
    if _table_exists("attachment_chunks"):
        _add_column_if_missing("attachment_chunks", "embedding_model", "VARCHAR(255)")
        _add_column_if_missing("attachment_chunks", "embedding_dim", "INTEGER")
        _add_column_if_missing("attachment_chunks", "vectorstore_collection", "VARCHAR(255)")


def _ensure_user_settings(default_user_id: int):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO user_settings (user_id, theme, use_docs_default)
                VALUES (:uid, NULL, 1)
                """
            ),
            {"uid": default_user_id},
        )


def _ensure_user_settings_columns():
    if _table_exists("user_settings"):
        _add_column_if_missing("user_settings", "embedding_model", "VARCHAR(64)")


def run_migrations() -> int:
    """
    Apply safe, idempotent migrations and return the default local user id.
    """
    _ensure_tables_exist()
    _ensure_meta_column()
    default_user_id = ensure_default_user()
    if _conversations_need_rebuild():
        _rebuild_conversations_table(default_user_id)
    else:
        _ensure_conversation_columns()
    _ensure_conversation_index()
    _ensure_attachment_metadata_columns()
    _copy_documents_to_attachments()
    _ensure_user_settings_columns()
    _ensure_user_settings(default_user_id)
    return default_user_id
