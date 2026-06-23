"""
scheduler.py — Background job scheduler using APScheduler.
Runs in-process with FastAPI — no separate worker needed.

Jobs:
  1. generate_recurring_invoices() — daily at 07:00 UTC
     Creates invoices for all active recurring configs due today.
  2. send_payment_reminders()     — daily at 08:00 UTC
     Sends email reminders for invoices due in 3 days or overdue today.
"""
import logging
from datetime import date, timedelta, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Invoice, LineItem, RecurringInvoice, RecurringLineItem, InvoiceReminder, User
from .email import send_reminder_email

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


def _advance_date(d: date, freq: str) -> date:
    if freq == "weekly":
        return d + timedelta(weeks=1)
    elif freq == "monthly":
        # Same day next month (clamp to month-end)
        month = d.month + 1 if d.month < 12 else 1
        year  = d.year if d.month < 12 else d.year + 1
        day   = min(d.day, [31,28,31,30,31,30,31,31,30,31,30,31][month-1])
        return date(year, month, day)
    elif freq == "quarterly":
        month = d.month + 3 if d.month <= 9 else (d.month + 3 - 12)
        year  = d.year if d.month <= 9 else d.year + 1
        day   = min(d.day, [31,28,31,30,31,30,31,31,30,31,30,31][month-1])
        return date(year, month, day)
    elif freq == "yearly":
        return date(d.year + 1, d.month, d.day)
    return d + timedelta(days=30)


def _next_invoice_number(db: Session, user_id: int) -> str:
    from .utils import next_sequence_number
    nums = [n for (n,) in db.query(Invoice.invoice_number)
            .filter(Invoice.user_id == user_id, Invoice.is_template == False).all()]
    return next_sequence_number(nums, "INV")


async def generate_recurring_invoices():
    """Generate invoices for all active recurring configs due today or earlier."""
    today = date.today()
    db: Session = SessionLocal()
    generated = 0
    try:
        due = db.query(RecurringInvoice).filter(
            RecurringInvoice.active    == True,
            RecurringInvoice.next_date <= today,
        ).all()

        for rec in due:
            # Check end date
            if rec.end_date and today > rec.end_date:
                rec.active = False
                continue

            import uuid
            inv = Invoice(
                user_id        = rec.user_id,
                client_id      = rec.client_id,
                invoice_number = _next_invoice_number(db, rec.user_id),
                due_date       = today + timedelta(days=30),
                currency       = rec.currency,
                category       = rec.category,
                notes          = rec.notes,
                payment_note   = rec.payment_note,
                template       = rec.template,
                status         = "unpaid",
                is_template    = False,
                view_token     = str(uuid.uuid4()),
            )
            db.add(inv); db.flush()

            for item in rec.line_items:
                db.add(LineItem(
                    invoice_id  = inv.id,
                    description = item.description,
                    quantity    = item.quantity,
                    unit_price  = item.unit_price,
                ))

            rec.next_date = _advance_date(rec.next_date, rec.frequency)
            generated += 1

        db.commit()
        if generated:
            logger.info(f"Scheduler: generated {generated} recurring invoice(s)")
    except Exception as e:
        logger.error(f"Scheduler error (recurring): {e}")
        db.rollback()
    finally:
        db.close()


async def send_payment_reminders():
    """Send reminder emails for invoices due in 3 days or overdue by 1 day."""
    today       = date.today()
    due_in_3    = today + timedelta(days=3)
    overdue_day = today - timedelta(days=1)
    db: Session = SessionLocal()
    sent = 0

    try:
        # Due soon
        due_soon = db.query(Invoice).filter(
            Invoice.status            == "unpaid",
            Invoice.is_template       == False,
            Invoice.reminders_enabled == True,
            Invoice.due_date          == due_in_3,
        ).all()

        for inv in due_soon:
            already = db.query(InvoiceReminder).filter(
                InvoiceReminder.invoice_id    == inv.id,
                InvoiceReminder.reminder_type == "due_soon",
            ).first()
            if not already and inv.client.email:
                ok = send_reminder_email(inv, "due_soon")
                if ok:
                    db.add(InvoiceReminder(invoice_id=inv.id, reminder_type="due_soon"))
                    sent += 1

        # Overdue (only send once — day after due date)
        overdue = db.query(Invoice).filter(
            Invoice.status            == "unpaid",
            Invoice.is_template       == False,
            Invoice.reminders_enabled == True,
            Invoice.due_date          == overdue_day,
        ).all()

        for inv in overdue:
            already = db.query(InvoiceReminder).filter(
                InvoiceReminder.invoice_id    == inv.id,
                InvoiceReminder.reminder_type == "overdue",
            ).first()
            if not already and inv.client.email:
                ok = send_reminder_email(inv, "overdue")
                if ok:
                    db.add(InvoiceReminder(invoice_id=inv.id, reminder_type="overdue"))
                    sent += 1

        db.commit()
        if sent:
            logger.info(f"Scheduler: sent {sent} payment reminder(s)")
    except Exception as e:
        logger.error(f"Scheduler error (reminders): {e}")
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(generate_recurring_invoices, CronTrigger(hour=7,  minute=0), id="recurring")
    scheduler.add_job(send_payment_reminders,      CronTrigger(hour=8,  minute=0), id="reminders")
    scheduler.start()
    logger.info("APScheduler started — recurring invoices at 07:00 UTC, reminders at 08:00 UTC")


def stop_scheduler():
    scheduler.shutdown(wait=False)
