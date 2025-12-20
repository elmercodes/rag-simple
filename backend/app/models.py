# backend/app/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .db import Base


# ---- Models ----
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(255), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversations = relationship("Conversation", back_populates="user")
    documents = relationship(
        "Document",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    documents = relationship(
        "Document",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


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


# ---- Relationships ----
class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "file_hash",
            name="uq_documents_conversation_file_hash",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Duplicate user_id on documents for multi-tenant safety and easier auth swap later.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(255), nullable=True)
    file_hash = Column(String(255), nullable=False)
    embedding_model = Column(String(255), nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    vectorstore_collection = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="documents")
    conversation = relationship("Conversation", back_populates="documents")
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(Integer, primary_key=True, index=True)
    # Duplicate user/conversation for multi-tenant safety and future auth changes.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id"),
        nullable=False,
        index=True,
    )
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
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

    document = relationship("Document", back_populates="chunks")
