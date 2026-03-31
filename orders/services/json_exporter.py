"""
注文書JSON生成 — 実務連携用

PDF生成(pdf_generator.py)と同じOrderインスタンスからデータを展開し、
PDFとの完全な整合性を保証する。
"""
from core.domain.models import CompanyInfo


def generate_order_json(order):
    """
    Orderオブジェクトから実務連携用のJSONデータ(dict)を生成する。

    PDFのgenerate_order_pdf()と同じorder, order.items, CompanyInfoを
    データソースとして使用し、値の乖離を防ぐ。
    """
    company = CompanyInfo.objects.first()

    # 甲乙の担当者（PDFと同じロジック）
    kou_res = order.甲_責任者 or (company.responsible_person if company else '')
    kou_cnt = order.甲_担当者 or (company.contact_person if company else '')
    otsu_res = order.乙_責任者 or order.partner.responsible_person
    otsu_cnt = order.乙_担当者 or order.partner.contact_person

    items = []
    total_amount = 0
    for item in order.items.all():
        items.append({
            'person_name': item.person_name or '作業担当者',
            'effort': float(item.effort),
            'base_fee': item.base_fee,
            'quantity': item.quantity,
            'amount': item.price,
            'ses_extension': {
                'time_lower_limit': float(item.time_lower_limit),
                'time_upper_limit': float(item.time_upper_limit),
                'shortage_rate': item.shortage_rate,
                'excess_rate': item.excess_rate,
            },
        })
        total_amount += item.price

    return {
        'document_type': 'ORDER',
        'order_id': order.order_id,
        'order_date': order.order_date.isoformat(),
        'status': order.status,
        'buyer': {
            'name': company.name if company else '',
            'postal_code': company.postal_code if company else '',
            'address': company.address if company else '',
            'tel': company.tel if company else '',
            'registration_number': company.registration_no if company else '',
            'responsible_person': kou_res,
            'contact_person': kou_cnt,
        },
        'seller': {
            'name': order.partner.name,
            'postal_code': order.partner.postal_code,
            'address': order.partner.address,
            'tel': order.partner.tel,
            'responsible_person': otsu_res,
            'contact_person': otsu_cnt,
        },
        'order_detail': {
            'project_name': order.project.name if order.project else '',
            'project_id': order.project.project_id if order.project else '',
            'service_period': {
                'start_date': order.work_start.isoformat(),
                'end_date': order.work_end.isoformat(),
            },
            'work_supervisor': order.作業責任者,
            'workplace': order.workplace.name if order.workplace else '',
            'deliverable': order.deliverable_text,
            'payment_condition': order.payment_condition,
        },
        'items': items,
        'summary': {
            'total_amount': total_amount,
        },
        'contract_terms': order.contract_items,
    }
