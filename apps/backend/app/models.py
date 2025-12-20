# backend/app/models.py
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


# ---- Models ----
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user")
    attachments = relationship(
        "Attachment",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    settings = relationship(
        "UserSettings",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    is_pinned = Column(Boolean, default=False, nullable=False)
    pinned_at = Column(DateTime, nullable=True)
    pinned_order = Column(Integer, nullable=True)
    use_docs_default = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    attachments = relationship(
        "Attachment",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    theme = Column(String(50), nullable=True)
    use_docs_default = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="settings")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    role = Column(String(10))  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    meta = Column(JSON, nullable=True)  # structured per-message metadata (e.g., retrieved excerpts)

    conversation = relationship("Conversation", back_populates="messages")
    routing_decision = relationship(
        "RoutingDecision",
        back_populates="message",
        uselist=False,
        cascade="all, delete-orphan",
    )


class RoutingDecision(Base):
    __tablename__ = "routing_decisions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False, unique=True)
    answer_mode = Column(String(20), nullable=False)  # "rag" | "direct"
    reason = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="routing_decision")


# ---- Attachments ----
class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "file_hash",
            name="uq_attachments_conversation_file_hash",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Duplicate user_id for multi-tenant safety and easier auth swap later.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=True)
    path = Column(String(1024), nullable=True)
    file_hash = Column(String(255), nullable=False)
    embedding_model = Column(String(255), nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    vectorstore_collection = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="attachments")
    conversation = relationship("Conversation", back_populates="attachments")
    chunks = relationship(
        "AttachmentChunk",
        back_populates="attachment",
        cascade="all, delete-orphan",
    )


class AttachmentChunk(Base):
    __tablename__ = "attachment_chunks"

    id = Column(Integer, primary_key=True, index=True)
    # Duplicate user/conversation for multi-tenant safety and future auth changes.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    attachment_id = Column(Integer, ForeignKey("attachments.id"), nullable=False, index=True)
    chunk_id = Column(String(255), nullable=False, unique=True)
    chunk_text = Column(Text, nullable=False)
    page = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=True)
    section = Column(String(255), nullable=True)
    preview = Column(Text, nullable=True)
    char_len = Column(Integer, nullable=True)
    embedding_model = Column(String(255), nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    vectorstore_collection = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    attachment = relationship("Attachment", back_populates="chunks")
