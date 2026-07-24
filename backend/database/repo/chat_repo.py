import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlmodel import Session, desc, func, select

from database.models import ChatMessage, ChatSession, get_engine


class ChatRepository:
    def __init__(self):
        self.engine = get_engine()

    def list_sessions(self, patient_id: str) -> List[Dict]:
        with Session(self.engine) as session:
            statement = select(ChatSession).where(
                ChatSession.patient_id == patient_id,
                ChatSession.is_archived == False
            ).order_by(desc(ChatSession.updated_at))
            sessions = session.exec(statement).all()

            return [self._session_summary(session, chat_session) for chat_session in sessions]

    def create_session(self, patient_id: str, title: Optional[str] = None) -> Dict:
        with Session(self.engine) as session:
            chat_session = ChatSession(
                patient_id=patient_id,
                title=title or "New conversation",
            )
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            return self._session_summary(session, chat_session)

    def get_session(
        self,
        patient_id: str,
        session_id: str,
        include_messages: bool = True
    ) -> Optional[Dict]:
        with Session(self.engine) as session:
            statement = select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.patient_id == patient_id,
                ChatSession.is_archived == False
            )
            chat_session = session.exec(statement).first()
            if not chat_session:
                return None

            result = self._session_summary(session, chat_session)

            if include_messages:
                message_statement = select(ChatMessage).where(
                    ChatMessage.session_id == chat_session.id
                ).order_by(ChatMessage.created_at)
                messages = session.exec(message_statement).all()
                result["messages"] = [self._message_to_dict(message) for message in messages]
                result["message_count"] = len(messages)

            return result

    def append_exchange(
        self,
        patient_id: str,
        session_id: str,
        user_content: str,
        assistant_content: str,
        user_timestamp: Optional[str] = None,
        assistant_timestamp: Optional[str] = None,
        user_metadata: Optional[Dict[str, Any]] = None,
        assistant_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if not chat_session or chat_session.patient_id != patient_id:
                return False

            user_time = self._parse_timestamp(user_timestamp) or datetime.utcnow()
            assistant_time = self._parse_timestamp(assistant_timestamp) or datetime.utcnow()

            user_message = ChatMessage(
                session_id=session_id,
                patient_id=patient_id,
                role="user",
                content=user_content,
                metadata_json=self._safe_json_dumps(user_metadata),
                created_at=user_time,
            )
            assistant_message = ChatMessage(
                session_id=session_id,
                patient_id=patient_id,
                role="assistant",
                content=assistant_content,
                metadata_json=self._safe_json_dumps(assistant_metadata),
                created_at=assistant_time,
            )

            session.add(user_message)
            session.add(assistant_message)

            if not chat_session.title or chat_session.title.strip().lower() == "new conversation":
                chat_session.title = self._derive_title_from_text(user_content)
            chat_session.updated_at = assistant_time

            session.add(chat_session)
            session.commit()
            return True

    def ensure_session(self, patient_id: str, session_id: Optional[str]) -> Dict:
        if session_id:
            existing = self.get_session(patient_id=patient_id, session_id=session_id, include_messages=False)
            if existing:
                return existing
        return self.create_session(patient_id=patient_id)

    def _session_summary(self, session: Session, chat_session: ChatSession) -> Dict:
        count_statement = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == chat_session.id)
        count_result = session.exec(count_statement).first()
        message_count = int(count_result or 0)

        latest_message_statement = select(ChatMessage).where(
            ChatMessage.session_id == chat_session.id
        ).order_by(desc(ChatMessage.created_at)).limit(1)
        latest_message = session.exec(latest_message_statement).first()

        preview = (latest_message.content or "").strip() if latest_message else ""
        if len(preview) > 180:
            preview = f"{preview[:177]}..."

        return {
            "id": chat_session.id,
            "patient_id": chat_session.patient_id,
            "title": chat_session.title or "New conversation",
            "created_at": chat_session.created_at.isoformat() if chat_session.created_at else None,
            "updated_at": chat_session.updated_at.isoformat() if chat_session.updated_at else None,
            "message_count": message_count,
            "last_message_preview": preview or None,
            "last_message_at": (
                latest_message.created_at.isoformat()
                if latest_message and latest_message.created_at else None
            ),
        }

    def _message_to_dict(self, message: ChatMessage) -> Dict:
        metadata = None
        if message.metadata_json:
            try:
                metadata = json.loads(message.metadata_json)
            except json.JSONDecodeError:
                metadata = None

        return {
            "id": message.id,
            "session_id": message.session_id,
            "patient_id": message.patient_id,
            "role": message.role,
            "content": message.content,
            "metadata": metadata,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }

    def _derive_title_from_text(self, text: str) -> str:
        compact = " ".join((text or "").split()).strip()
        if not compact:
            return "New conversation"
        if len(compact) <= 46:
            return compact
        return f"{compact[:43]}..."

    def _parse_timestamp(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _safe_json_dumps(self, value: Optional[Dict[str, Any]]) -> Optional[str]:
        if value is None:
            return None
        try:
            return json.dumps(value, ensure_ascii=True, default=str)
        except Exception:
            return None
