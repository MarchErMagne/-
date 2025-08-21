from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, JSON, Float, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class CampaignStatus(enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"

class SenderType(enum.Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    SMS = "sms"
    VIBER = "viber"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    language_code = Column(String(10), default="ru")
    is_premium = Column(Boolean, default=False)
    subscription_plan = Column(String(50))
    subscription_expires = Column(DateTime)
    subscription_status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.EXPIRED)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    senders = relationship("Sender", back_populates="user", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan = Column(String(50), nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    starts_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=False)
    auto_renew = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    invoice_id = Column(String(255), unique=True)
    amount = Column(Integer)  # в центах
    currency = Column(String(10), default="USD")
    status = Column(String(50))
    plan = Column(String(50))
    crypto_pay_id = Column(String(255))
    created_at = Column(DateTime, default=func.now())
    paid_at = Column(DateTime)
    
    # Relationships
    user = relationship("User", back_populates="payments")

class Sender(Base):
    __tablename__ = "senders"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(Enum(SenderType), nullable=False)
    config = Column(JSON)  # Конфигурация отправителя
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_used = Column(DateTime)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="senders")

class Contact(Base):
    __tablename__ = "contacts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    identifier = Column(String(255), nullable=False)  # email, phone, telegram_id
    type = Column(Enum(SenderType), nullable=False)
    first_name = Column(String(255))
    last_name = Column(String(255))
    tags = Column(JSON)
    metadata = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="contacts")

class Campaign(Base):
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    type = Column(Enum(SenderType), nullable=False)
    sender_id = Column(Integer, ForeignKey("senders.id"))
    subject = Column(String(500))
    message = Column(Text, nullable=False)
    status = Column(Enum(CampaignStatus), default=CampaignStatus.DRAFT)
    
    # Scheduling
    scheduled_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Settings
    batch_size = Column(Integer, default=10)
    delay_seconds = Column(Integer, default=1)
    retry_failed = Column(Boolean, default=True)
    
    # Stats
    total_contacts = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="campaigns")
    logs = relationship("CampaignLog", back_populates="campaign", cascade="all, delete-orphan")

class CampaignLog(Base):
    __tablename__ = "campaign_logs"
    
    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    contact_identifier = Column(String(255), nullable=False)
    status = Column(String(50))  # sent, failed, delivered, opened, clicked
    error_message = Column(Text)
    sent_at = Column(DateTime, default=func.now())
    
    # Analytics
    opened_at = Column(DateTime)
    clicked_at = Column(DateTime)
    
    # Relationships
    campaign = relationship("Campaign", back_populates="logs")

class FileUpload(Base):
    __tablename__ = "file_uploads"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer)
    file_type = Column(String(100))
    upload_path = Column(String(500))
    processed = Column(Boolean, default=False)
    contacts_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

class Analytics(Base):
    __tablename__ = "analytics"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"))
    event_type = Column(String(50))  # sent, delivered, opened, clicked, bounced
    contact_identifier = Column(String(255))
    timestamp = Column(DateTime, default=func.now())
    metadata = Column(JSON)

class AIPrompt(Base):
    __tablename__ = "ai_prompts"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    prompt = Column(Text, nullable=False)
    response = Column(Text)
    type = Column(String(50))  # message_generation, spam_check, etc
    created_at = Column(DateTime, default=func.now())