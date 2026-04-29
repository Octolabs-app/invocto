"""
models.py — SQLAlchemy ORM models for the Tax-Ready Invoice app.

Tables:
  - users        : registered user accounts
  - clients      : clients belonging to a user
  - invoices     : invoices created by a user for a client
  - line_items   : individual line items on an invoice
  - expenses     : business expenses logged by a user
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    """Registered user account. Passwords are stored hashed — never plain text."""
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Relationships — cascade delete removes children when user is deleted
    clients  = relationship("Client",  back_populates="user", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="user", cascade="all, delete-orphan")
    expenses = relationship("Expense", back_populates="user", cascade="all, delete-orphan")


class Client(Base):
    """A client that belongs to a user."""
    __tablename__ = "clients"

    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    name       = Column(String(255), nullable=False)
    email      = Column(String(255), nullable=True)
    address    = Column(Text, nullable=True)
    phone      = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user     = relationship("User",    back_populates="clients")
    invoices = relationship("Invoice", back_populates="client")


class Invoice(Base):
    """
    An invoice created by a user for a client.

    status: "unpaid" | "paid"
    currency: "USD" | "EUR" | "GBP" | "MUR"
    category: AI-suggested or manually chosen service category
    """
    __tablename__ = "invoices"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    client_id      = Column(Integer, ForeignKey("clients.id"), nullable=False)
    invoice_number = Column(String(50), nullable=False)      # e.g. INV-0001
    status         = Column(String(20), default="unpaid")    # "paid" or "unpaid"
    due_date       = Column(Date, nullable=False)
    payment_date   = Column(Date, nullable=True)             # set when marked paid
    currency       = Column(String(10), default="USD")
    category       = Column(String(50), default="Other")
    notes          = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)

    user       = relationship("User",     back_populates="invoices")
    client     = relationship("Client",   back_populates="invoices")
    line_items = relationship("LineItem", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def total(self) -> float:
        """Sum of all line item totals (quantity × unit_price)."""
        return sum(item.quantity * item.unit_price for item in self.line_items)

    @property
    def is_overdue(self) -> bool:
        """True if unpaid and past due date."""
        return self.status == "unpaid" and self.due_date < date.today()


class LineItem(Base):
    """A single line on an invoice (service description, qty, price)."""
    __tablename__ = "line_items"

    id          = Column(Integer, primary_key=True, index=True)
    invoice_id  = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    description = Column(String(500), nullable=False)
    quantity    = Column(Float, default=1.0)
    unit_price  = Column(Float, default=0.0)

    invoice = relationship("Invoice", back_populates="line_items")

    @property
    def line_total(self) -> float:
        return self.quantity * self.unit_price


class Expense(Base):
    """A business expense logged by a user."""
    __tablename__ = "expenses"

    id          = Column(Integer, primary_key=True, index=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    date        = Column(Date, nullable=False)
    description = Column(String(500), nullable=False)
    amount      = Column(Float, default=0.0)
    category    = Column(String(50), default="Other")
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="expenses")
