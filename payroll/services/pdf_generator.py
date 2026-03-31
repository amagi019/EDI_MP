"""
給与明細PDF生成サービス
"""
import io
from django.template.loader import render_to_string
from core.domain.models import CompanyInfo


def generate_payslip_pdf(payroll):
    """
    給与明細書PDFを生成してバイトストリームを返す。
    """
    company = CompanyInfo.objects.first()

    context = {
        'payroll': payroll,
        'employee': payroll.employee,
        'company': company,
    }

    html_string = render_to_string(
        'payroll/payslip_pdf.html', context)
    from weasyprint import HTML
    html = HTML(string=html_string)
    pdf_bytes = html.write_pdf()

    return io.BytesIO(pdf_bytes)
