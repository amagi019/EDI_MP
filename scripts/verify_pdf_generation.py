
import os
import sys
import django
import datetime
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'EDI_MP.settings')
django.setup()

from django.db import transaction
from django.conf import settings
from core.models import Customer, CompanyInfo
from orders.models import Order, OrderItem, Project, Workplace, PaymentTerm, ContractTerm
from invoices.models import Invoice, InvoiceItem
from invoices.services.pdf_generator import generate_invoice_pdf, generate_payment_notice_pdf
from orders.services.pdf_generator import generate_order_pdf, generate_acceptance_pdf

def verify_pdf_generation():
    print("Starting PDF generation verification...")
    output_dir = "verification_outputs"
    os.makedirs(output_dir, exist_ok=True)

    try:
        with transaction.atomic():
            # 1. Create Dummy Data
            print("Creating dummy data...")
            
            # Company Info (Ensure at least one exists)
            if not CompanyInfo.objects.exists():
                CompanyInfo.objects.create(name="Test Company")

            # Customer
            customer = Customer.objects.create(
                name="Test Customer Ltd.",
                email="test@example.com",
                postal_code="123-4567",
                address="Tokyo, Japan",
                customer_id="TEST001"
            )

            # Project
            project = Project.objects.create(name="Test Project")

            # Order
            order = Order.objects.create(
                customer=customer,
                project=project,
                work_start=datetime.date.today(),
                work_end=datetime.date.today() + datetime.timedelta(days=30),
                base_fee=100000,
                deliverable_text="Monthly Report",
                payment_condition="End of next month",
                contract_items="Standard Terms",
                order_date=datetime.date.today(),
                order_end_ym=datetime.date.today()
            )

            # Order Item
            OrderItem.objects.create(
                order=order,
                person_name="Test Worker",
                base_fee=50000,
                effort=Decimal("1.0"),
                time_lower_limit=140,
                time_upper_limit=180,
                actual_hours=160
            )

            # Invoice
            invoice = Invoice.objects.create(
                order=order,
                target_month=datetime.date.today(),
                department="System Dev Dept"
            )

            # Invoice Item
            InvoiceItem.objects.create(
                invoice=invoice,
                person_name="Test Worker",
                base_fee=50000,
                work_time=160,
                time_lower_limit=140,
                time_upper_limit=180,
                item_subtotal=50000
            )
            
            invoice.subtotal_amount = 50000
            invoice.tax_amount = 5000
            invoice.total_amount = 55000
            invoice.save()

            print(f"Order ID: {order.order_id}")
            print(f"Invoice No: {invoice.invoice_no}")

            # 2. Generate PDFs
            print("Generating Invoice PDF...")
            invoice_pdf = generate_invoice_pdf(invoice)
            with open(os.path.join(output_dir, "test_invoice.pdf"), "wb") as f:
                f.write(invoice_pdf.read())
            
            print("Generating Payment Notice PDF...")
            payment_notice_pdf = generate_payment_notice_pdf(invoice)
            with open(os.path.join(output_dir, "test_payment_notice.pdf"), "wb") as f:
                f.write(payment_notice_pdf.read())

            print("Generating Order PDF...")
            order_pdf = generate_order_pdf(order)
            with open(os.path.join(output_dir, "test_order.pdf"), "wb") as f:
                f.write(order_pdf.read())
                
            print("Generating Acceptance PDF...")
            acceptance_pdf = generate_acceptance_pdf(order)
            with open(os.path.join(output_dir, "test_acceptance.pdf"), "wb") as f:
                f.write(acceptance_pdf.read())

            print("PDF generation successful. Files saved in 'verification_outputs/'.")
            
            # Rollback transaction to clean up DB
            raise Exception("Verification Complete (Rolling back DB changes)")

    except Exception as e:
        if "Verification Complete" in str(e):
            print(str(e))
        else:
            print(f"Error during verification: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    verify_pdf_generation()
