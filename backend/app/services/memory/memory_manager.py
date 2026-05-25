from datetime import datetime
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.session_model import ChatSession, ChatMessage
from app.services.llm.ollama_client import get_ollama_client

logger = get_logger(__name__)
settings = get_settings()

SUMMARIZE_SYSTEM = """You are summarizing a pricing analysis conversation.
Write a concise paragraph (3-5 sentences) capturing: the datasets/documents being analyzed,
the pricing questions explored, key findings, and any decisions made.
Focus on facts, not conversation structure."""


async def get_or_create_session(
    session_id: str | None,
    tenant_id: str,
    db: AsyncSession,
) -> ChatSession:
    if session_id:
        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == uuid.UUID(session_id),
                ChatSession.tenant_id == tenant_id,
            )
        )
        session = result.scalar_one_or_none()
        if session:
            session.last_active_at = datetime.utcnow()
            return session

    # Create new session
    session = ChatSession(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        messages=[],
        context_summary=None,
        turn_count=0,
    )
    db.add(session)
    await db.flush()
    logger.info("session_created", session_id=str(session.id), tenant=tenant_id)
    return session


async def add_turn(
    session: ChatSession,
    user_message: str,
    assistant_message: str,
    db: AsyncSession,
) -> str:
    """
    Add a user/assistant turn to the session.
    Memory strategy:
    - Keep last SESSION_WINDOW_TURNS full turns in `messages`
    - After SESSION_SUMMARIZE_AFTER turns, summarize the oldest turns and store in context_summary
    Returns the context string to inject into the next LLM call.
    """
    messages: list = list(session.messages or [])

    messages.append({"role": "user", "content": user_message, "turn": session.turn_count})
    messages.append({"role": "assistant", "content": assistant_message, "turn": session.turn_count})
    session.turn_count += 1

    # Persist to chat_messages table for full history
    db.add(ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="user",
        content=user_message,
        turn_index=session.turn_count - 1,
    ))
    db.add(ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role="assistant",
        content=assistant_message,
        turn_index=session.turn_count - 1,
    ))

    # Summarize if we exceed the threshold
    window = settings.session_window_turns * 2  # pairs of messages
    summarize_at = settings.session_summarize_after * 2

    if len(messages) > summarize_at:
        old_messages = messages[:-window]
        recent_messages = messages[-window:]

        # Summarize old messages using local LLM
        old_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:500]}" for m in old_messages
        )
        ollama = get_ollama_client()
        new_summary = await ollama.generate(
            prompt=f"Previous summary:\n{session.context_summary or 'None'}\n\nNew conversation to summarize:\n{old_text}",
            system=SUMMARIZE_SYSTEM,
            temperature=0.0,
        )
        session.context_summary = new_summary
        messages = recent_messages

    session.messages = messages
    session.updated_at = datetime.utcnow()

    context = _build_context_string(session)
    return context


def _build_context_string(session: ChatSession) -> str:
    """Build the context string to inject into the next LLM call."""
    parts = []

    if session.context_summary:
        parts.append(f"Summary of earlier discussion:\n{session.context_summary}")

    recent = list(session.messages or [])[-settings.session_window_turns * 2:]
    if recent:
        convo = "\n".join(f"{m['role'].upper()}: {m['content'][:600]}" for m in recent)
        parts.append(f"Recent conversation:\n{convo}")

    return "\n\n".join(parts) if parts else ""


async def get_session_context(session: ChatSession) -> str:
    return _build_context_string(session)


async def update_session_datasets(
    session: ChatSession,
    dataset_ids: list[str],
    document_ids: list[str],
    db: AsyncSession,
) -> None:
    session.active_dataset_ids = dataset_ids
    session.active_document_ids = document_ids
    session.updated_at = datetime.utcnow()
