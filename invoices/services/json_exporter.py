"""
請求書JSON生成 — 実務連携用

請求書PDF生成と同じInvoiceインスタンスからデータを展開し、
PDFとの完全な整合性を保証する。
"""
from core.domain.models import CompanyInfo


def generate_invoice_json(invoice):
    """
    Invoiceオブジェクトから実務連携用のJSONデータ(dict)を生成する。

    PDFと同じinvoice, invoice.items, CompanyInfoをデータソースとして使用。
    """
    company = CompanyInfo.objects.first()
    order = invoice.order

    items = []
    for item in invoice.items.all():
        items.append({
            'person_name': item.person_name,
            'work_time': float(item.work_time),
            'base_fee': item.base_fee,
            'ses_extension': {
                'time_lower_limit': float(item.time_lower_limit),
                'time_upper_limit': float(item.time_upper_limit),
                'shortage_rate': item.shortage_rate,
                'excess_rate': item.excess_rate,
            },
            'excess_amount': item.excess_amount,
            'shortage_amount': item.shortage_amount,
            'item_subtotal': item.item_subtotal,
            'remarks': item.remarks,
        })

    return {
        'document_type': 'INVOICE',
        'invoice_no': invoice.invoice_no,
        'acceptance_no': invoice.acceptance_no,
        'issue_date': invoice.issue_date.isoformat(),
        'target_month': invoice.target_month.isoformat(),
        'status': invoice.status,
        'order_reference': {
            'order_id': order.order_id,
            'project_name': order.project.name if order.project else '',
            'project_id': order.project.project_id if order.project else '',
        },
        'supplier': {
            'name': company.name if company else '',
            'postal_code': company.postal_code if company else '',
            'address': company.address if company else '',
            'tel': company.tel if company else '',
            'registration_number': company.registration_no if company else '',
        },
        'customer': {
            'name': order.partner.name,
            'postal_code': order.partner.postal_code,
            'address': order.partner.address,
            'tel': order.partner.tel,
        },
        'items': items,
        'summary': {
            'subtotal_amount': invoice.subtotal_amount,
            'tax_amount': invoice.tax_amount,
            'total_amount': invoice.total_amount,
        },
        'payment': {
            'payment_deadline': invoice.payment_deadline.isoformat() if invoice.payment_deadline else None,
            'payment_date': invoice.payment_date.isoformat() if invoice.payment_date else None,
        },
    }
