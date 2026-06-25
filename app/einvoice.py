"""
einvoice.py — Universal structured e-invoice export.

Generates UBL 2.1 XML aligned with the EN 16931 semantic model and Peppol
BIS Billing 3.0 — the international baseline that most national e-invoicing
mandates (EU member states, Peppol countries, and a growing number beyond)
build on. This is the structured-data foundation; country-specific transmission
(Peppol Access Point, India IRP, Italy SDI, Saudi ZATCA, …) layers on top per
jurisdiction.

Kept dependency-free (stdlib only) and side-effect-free: it turns an Invoice
ORM object into a string. All dynamic text is XML-escaped.
"""
from datetime import date
from xml.sax.saxutils import escape, quoteattr


def _money(v) -> str:
    return f"{float(v or 0):.2f}"


def _q(v) -> str:
    """Format a quantity without trailing zeros (UBL allows decimals)."""
    f = float(v or 0)
    return f"{f:g}"


def _t(v) -> str:
    return escape(str(v)) if v not in (None, "") else ""


def _attr(v) -> str:
    return quoteattr(str(v or ""))


def _country(code: str) -> str:
    """Return a valid-ish ISO 3166-1 alpha-2 code, or 'ZZ' (unknown)."""
    c = (code or "").strip().upper()
    return c if (len(c) == 2 and c.isalpha()) else "ZZ"


def _party(role_tag: str, name: str, vat: str = "", address: str = "",
           email: str = "", phone: str = "", country: str = "") -> str:
    """Build a cac:AccountingSupplierParty / ...CustomerParty block."""
    street = (address or "").splitlines()[0] if address else ""
    tax_block = ""
    if vat:
        tax_block = f"""
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{_t(vat)}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>"""
    contact = ""
    if email or phone:
        contact = f"""
      <cac:Contact>
        {f'<cbc:Telephone>{_t(phone)}</cbc:Telephone>' if phone else ''}
        {f'<cbc:ElectronicMail>{_t(email)}</cbc:ElectronicMail>' if email else ''}
      </cac:Contact>"""
    return f"""
  <cac:{role_tag}>
    <cac:Party>
      <cac:PartyName><cbc:Name>{_t(name) or 'N/A'}</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>{_t(street)}</cbc:StreetName>
        <cac:Country><cbc:IdentificationCode>{_country(country)}</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>{tax_block}
      <cac:PartyLegalEntity><cbc:RegistrationName>{_t(name) or 'N/A'}</cbc:RegistrationName></cac:PartyLegalEntity>{contact}
    </cac:Party>
  </cac:{role_tag}>"""


def invoice_to_ubl(invoice, profile=None, user_email: str = "") -> str:
    """Serialise an Invoice into an EN 16931-compliant UBL 2.1 XML string."""
    cur = invoice.currency or "USD"
    issue = (invoice.created_at.date() if getattr(invoice, "created_at", None) else date.today()).isoformat()
    due = invoice.due_date.isoformat() if invoice.due_date else issue

    subtotal = invoice.subtotal
    discount = invoice.discount_amount
    taxable = round(subtotal - discount, 2)
    tax_amount = invoice.tax_amount
    tax_rate = float(invoice.tax_rate or 0.0)
    late_fee = float(invoice.late_fee_amount or 0.0)
    payable = invoice.total
    tax_cat = "S" if tax_rate > 0 else "Z"  # Standard-rated vs Zero-rated

    seller_name = (profile.business_name if profile and profile.business_name else (user_email or "Your Business"))
    seller_vat = (profile.business_reg_number if profile else "") or ""
    seller_addr = (profile.business_address if profile else "") or ""
    seller_email = ((profile.business_email if profile else "") or user_email) or ""
    seller_phone = (profile.business_phone if profile else "") or ""
    seller_country = (profile.country if profile else "") or ""

    client = invoice.client
    buyer_name = client.name if client else "N/A"
    buyer_addr = (client.address if client else "") or ""
    buyer_email = (client.email if client else "") or ""
    buyer_phone = (client.phone if client else "") or ""

    # Line items
    lines_xml = ""
    for idx, item in enumerate(invoice.line_items, start=1):
        line_total = round(item.quantity * item.unit_price, 2)
        lines_xml += f"""
  <cac:InvoiceLine>
    <cbc:ID>{idx}</cbc:ID>
    <cbc:InvoicedQuantity unitCode="C62">{_q(item.quantity)}</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="{cur}">{_money(line_total)}</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>{_t(item.description) or 'Item'}</cbc:Name>
      <cac:ClassifiedTaxCategory>
        <cbc:ID>{tax_cat}</cbc:ID>
        <cbc:Percent>{_money(tax_rate)}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:ClassifiedTaxCategory>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="{cur}">{_money(item.unit_price)}</cbc:PriceAmount>
    </cac:Price>
  </cac:InvoiceLine>"""

    # Document-level discount as an AllowanceCharge (BG-20)
    allowance_xml = ""
    allowance_total = "0.00"
    if discount and discount > 0:
        allowance_total = _money(discount)
        allowance_xml = f"""
  <cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>Discount</cbc:AllowanceChargeReason>
    <cbc:Amount currencyID="{cur}">{_money(discount)}</cbc:Amount>
    <cac:TaxCategory>
      <cbc:ID>{tax_cat}</cbc:ID>
      <cbc:Percent>{_money(tax_rate)}</cbc:Percent>
      <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
    </cac:TaxCategory>
  </cac:AllowanceCharge>"""

    charge_xml = ""
    charge_total = "0.00"
    if late_fee and late_fee > 0:
        charge_total = _money(late_fee)
        charge_xml = f"""
  <cac:AllowanceCharge>
    <cbc:ChargeIndicator>true</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>Late fee</cbc:AllowanceChargeReason>
    <cbc:Amount currencyID="{cur}">{_money(late_fee)}</cbc:Amount>
    <cac:TaxCategory>
      <cbc:ID>{tax_cat}</cbc:ID>
      <cbc:Percent>{_money(tax_rate)}</cbc:Percent>
      <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
    </cac:TaxCategory>
  </cac:AllowanceCharge>"""

    tax_inclusive = round(taxable + tax_amount, 2)

    notes_xml = f"<cbc:Note>{_t(invoice.notes)}</cbc:Note>" if invoice.notes else ""
    payment_terms = f"""
  <cac:PaymentTerms><cbc:Note>{_t(invoice.payment_note)}</cbc:Note></cac:PaymentTerms>""" if invoice.payment_note else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:fdc:peppol.eu:2017:poacc:billing:3.0</cbc:CustomizationID>
  <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
  <cbc:ID>{_t(invoice.invoice_number)}</cbc:ID>
  <cbc:IssueDate>{issue}</cbc:IssueDate>
  <cbc:DueDate>{due}</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  {notes_xml}
  <cbc:DocumentCurrencyCode>{cur}</cbc:DocumentCurrencyCode>{_party('AccountingSupplierParty', seller_name, seller_vat, seller_addr, seller_email, seller_phone, seller_country)}{_party('AccountingCustomerParty', buyer_name, '', buyer_addr, buyer_email, buyer_phone)}{payment_terms}{allowance_xml}{charge_xml}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{cur}">{_money(tax_amount)}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="{cur}">{_money(taxable)}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="{cur}">{_money(tax_amount)}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:ID>{tax_cat}</cbc:ID>
        <cbc:Percent>{_money(tax_rate)}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="{cur}">{_money(subtotal)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="{cur}">{_money(taxable)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="{cur}">{_money(tax_inclusive)}</cbc:TaxInclusiveAmount>
    <cbc:AllowanceTotalAmount currencyID="{cur}">{allowance_total}</cbc:AllowanceTotalAmount>
    <cbc:ChargeTotalAmount currencyID="{cur}">{charge_total}</cbc:ChargeTotalAmount>
    <cbc:PayableAmount currencyID="{cur}">{_money(payable)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>{lines_xml}
</Invoice>"""
