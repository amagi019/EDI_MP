"""
PDF生成サービス（WeasyPrint）
"""
import io
from django.template.loader import render_to_string
from core.domain.models import CompanyInfo


def generate_billing_pdf(invoice):
    """
    請求書PDFを生成してバイトストリームを返す。
    """
    # 自社情報を取得
    company = invoice.company or CompanyInfo.objects.first()

    # 税率ごとの内訳
    tax_summary = invoice.tax_summary
    for rate, amounts in tax_summary.items():
        amounts['tax_fmt'] = f"{amounts['tax']:,}"

    context = {
        'invoice': invoice,
        'company': company,
        'items': invoice.items.all(),
        'subtotal': invoice.subtotal,
        'subtotal_fmt': f"{invoice.subtotal:,}",
        'tax_amount': invoice.tax_amount,
        'total': invoice.total,
        'total_fmt': f"{invoice.total:,}",
        'tax_summary': tax_summary,
    }

    html_string = render_to_string('billing/invoice_pdf.html', context)
    from weasyprint import HTML
    html = HTML(string=html_string)
    pdf_bytes = html.write_pdf()

    return io.BytesIO(pdf_bytes)
