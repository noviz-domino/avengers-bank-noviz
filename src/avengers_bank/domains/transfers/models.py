import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from avengers_bank.core.database import Base


class ClearingReceipt(Base):
    __tablename__ = "clearing_receipts"

    transfer_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    holder_name: Mapped[str] = mapped_column(String(50), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
