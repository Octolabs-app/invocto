"""
models.py — SQLAlchemy ORM models.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    clients  = relationship("Client",      back_populates="user", cascade="all, delete-orphan")
    invoices = relationship("Invoice",     back_populates="user", cascade="all, delete-orphan")
    expenses = relationship("Expense",     back_populates="user", cascade="all, delete-orphan")
    profile  = relationship("UserProfile", back_populates="user", cascade="all, delete-orphan", uselist=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    id                     = Column(Integer, primary_key=True, index=True)
    user_id                = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    business_name          = Column(String(255))
    business_reg_number    = Column(String(100))
    business_address       = Column(Text)
    business_email         = Column(String(255))
    business_phone         = Column(String(50))
    business_website       = Column(String(255))
    logo_base64            = Column(Text)
    invoice_template       = Column(String(20), default="minimal")
    payment_instructions   = Column(Text)
    bank_details           = Column(Text)
    paypal_email           = Column(String(255))
    plan                   = Column(String(20), default="free")
    stripe_customer_id     = Column(String(100))
    stripe_subscription_id = Column(String(100))
    plan_expires_at        = Column(DateTime)
    created_at             = Column(DateTime, default=datetime.utcnow)
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")

    @property
    def is_pro(self):
        return self.plan == "pro"


class Client(Base):
    __tablename__ = "clients"
    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    name       = Column(String(255), nullable=False)
    email      = Column(String(255))
    address    = Column(Text)
    phone      = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    user     = relationship("User",    back_populates="clients")
    invoices = relationship("Invoice", back_populates="client")


class Invoice(Base):
    __tablename__ = "invoices"
    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_id      = Column(Integer, ForeignKey("clients.id"), nullable=False)
    invoice_number = Column(String(50), nullable=False)
    status         = Column(String(20), default="unpaid")
    due_date       = Column(Date, nullable=False)
    payment_date   = Column(Date)
    currency       = Column(String(10), default="USD")
    category       = Column(String(50), default="Other")
    notes          = Column(Text)
    template       = Column(String(20), default="minimal")
    is_template    = Column(Boolean, default=False)
    template_name  = Column(String(100))
    payment_note   = Column(Text)
    created_at     = Column(DateTime, default=datetime.utcnow)

    user       = relationship("User",     back_populates="invoices")
    client     = relationship("Client",   back_populates="invoices")
    line_items = relationship("LineItem", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def total(self):
        return sum(item.quantity * item.unit_price for item in self.line_items)

    @property
    def is_overdue(self):
        return self.status == "unpaid" and self.due_date < date.today()


class LineItem(Base):
    __tablename__ = "line_items"
    id          = Column(Integer, primary_key=True, index=True)
    invoice_id  = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    description = Column(String(500), nullable=False)
    quantity    = Column(Float, default=1.0)
    unit_price  = Column(Float, default=0.0)

    invoice = relationship("Invoice", back_populates="line_items")

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Expense(Base):
    __tablename__ = "expenses"
    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    date        = Column(Date, nullable=False)
    description = Column(String(500), nullable=False)
    amount      = Column(Float, default=0.0)
    category    = Column(String(50), default="Other")
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="expenses")
