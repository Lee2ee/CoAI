from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..core.database import Base


class UserAIConfig(Base):
    __tablename__ = "user_ai_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(50), default="ollama")
    model: Mapped[str] = mapped_column(String(100), default="llama3.2")
    api_key: Mapped[str] = mapped_column(String(500), default="")
    ollama_url: Mapped[str] = mapped_column(String(255), default="http://localhost:11434")

    user: Mapped["User"] = relationship(back_populates="ai_config")
