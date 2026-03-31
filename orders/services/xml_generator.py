"""
注文書XML生成 — 中小企業共通EDI準拠

PDF生成(pdf_generator.py)と同じOrderインスタンスからデータを展開し、
PDFとの完全な整合性を保証する。
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom
import io

from core.domain.models import CompanyInfo


def generate_order_xml(order):
    """
    Orderオブジェクトから中小企業共通EDI準拠のXMLを生成する。

    PDFのgenerate_order_pdf()と同じorder, order.items, CompanyInfoを
    データソースとして使用し、値の乖離を防ぐ。
    """
    company = CompanyInfo.objects.first()

    # ルート要素
    root = ET.Element('OrderDocument')
    root.set('xmlns', 'urn:jp:co:edi:common:order:3')
    root.set('version', '3.0')

    # ─── ヘッダー ───
    header = ET.SubElement(root, 'OrderHeader')
    ET.SubElement(header, 'OrderID').text = order.order_id
    ET.SubElement(header, 'OrderDate').text = order.order_date.isoformat()
    ET.SubElement(header, 'DocumentType').text = 'ORDER'

    # ─── 発注者（甲 = 自社） ───
    buyer = ET.SubElement(root, 'Buyer')
    if company:
        ET.SubElement(buyer, 'Name').text = company.name
        ET.SubElement(buyer, 'PostalCode').text = company.postal_code
        ET.SubElement(buyer, 'Address').text = company.address
        ET.SubElement(buyer, 'Tel').text = company.tel
        ET.SubElement(buyer, 'Fax').text = company.fax
        if company.registration_no:
            ET.SubElement(buyer, 'RegistrationNumber').text = company.registration_no

    # 甲の担当者（PDFと同じロジック）
    kou_res = order.甲_責任者 or (company.responsible_person if company else '')
    kou_cnt = order.甲_担当者 or (company.contact_person if company else '')
    contacts_buyer = ET.SubElement(buyer, 'Contacts')
    ET.SubElement(contacts_buyer, 'ResponsiblePerson').text = kou_res
    ET.SubElement(contacts_buyer, 'ContactPerson').text = kou_cnt

    # ─── 受注者（乙 = パートナー） ───
    seller = ET.SubElement(root, 'Seller')
    partner = order.partner
    ET.SubElement(seller, 'Name').text = partner.name
    ET.SubElement(seller, 'PostalCode').text = partner.postal_code
    ET.SubElement(seller, 'Address').text = partner.address
    ET.SubElement(seller, 'Tel').text = partner.tel
    if hasattr(partner, 'fax') and partner.fax:
        ET.SubElement(seller, 'Fax').text = partner.fax

    # 乙の担当者（PDFと同じロジック）
    otsu_res = order.乙_責任者 or partner.responsible_person
    otsu_cnt = order.乙_担当者 or partner.contact_person
    contacts_seller = ET.SubElement(seller, 'Contacts')
    ET.SubElement(contacts_seller, 'ResponsiblePerson').text = otsu_res
    ET.SubElement(contacts_seller, 'ContactPerson').text = otsu_cnt

    # ─── 注文内容 ───
    order_detail = ET.SubElement(root, 'OrderDetail')

    # 業務名称（PDFテーブルの1行目と同じ）
    ET.SubElement(order_detail, 'ProjectName').text = (
        order.project.name if order.project else ''
    )

    # 作業期間（PDFテーブルの2行目と同じフォーマット）
    period = ET.SubElement(order_detail, 'ServicePeriod')
    ET.SubElement(period, 'StartDate').text = order.work_start.isoformat()
    ET.SubElement(period, 'EndDate').text = order.work_end.isoformat()

    # 作業責任者
    ET.SubElement(order_detail, 'WorkSupervisor').text = order.作業責任者

    # 作業場所
    ET.SubElement(order_detail, 'Workplace').text = (
        order.workplace.name if order.workplace else ''
    )

    # 納入物件
    ET.SubElement(order_detail, 'Deliverable').text = order.deliverable_text

    # 支払条件
    ET.SubElement(order_detail, 'PaymentCondition').text = order.payment_condition

    # ─── 明細行（PDFの_build_fee_tableと同じデータ） ───
    items_elem = ET.SubElement(root, 'OrderItems')
    total_amount = 0

    for item in order.items.all():
        line = ET.SubElement(items_elem, 'Item')
        ET.SubElement(line, 'PersonName').text = item.person_name or '作業担当者'
        ET.SubElement(line, 'Effort').text = str(float(item.effort))
        ET.SubElement(line, 'BaseFee').text = str(item.base_fee)
        ET.SubElement(line, 'Quantity').text = str(item.quantity)
        ET.SubElement(line, 'Amount').text = str(item.price)

        # SES拡張項目（精算条件）
        ext = ET.SubElement(line, 'SESExtension')
        ET.SubElement(ext, 'TimeLowerLimit').text = str(float(item.time_lower_limit))
        ET.SubElement(ext, 'TimeUpperLimit').text = str(float(item.time_upper_limit))
        ET.SubElement(ext, 'ShortageRate').text = str(item.shortage_rate)
        ET.SubElement(ext, 'ExcessRate').text = str(item.excess_rate)

        total_amount += item.price

    # ─── 合計 ───
    summary = ET.SubElement(root, 'OrderSummary')
    ET.SubElement(summary, 'TotalAmount').text = str(total_amount)

    # ─── 契約条項 ───
    ET.SubElement(root, 'ContractTerms').text = order.contract_items

    # XML文字列を整形して返す
    xml_str = ET.tostring(root, encoding='unicode', xml_declaration=False)
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8')

    return pretty_xml
