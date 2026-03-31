"""
請求書XML生成 — JP-PINT (Peppol準拠) フォーマット

請求書PDF生成と同じInvoiceインスタンスからデータを展開し、
PDFとの完全な整合性を保証する。
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom

from core.domain.models import CompanyInfo


def generate_invoice_xml(invoice):
    """
    Invoiceオブジェクトから JP-PINT準拠のXMLを生成する。

    PDFと同じinvoice, invoice.items, CompanyInfoをデータソースとして使用。
    """
    company = CompanyInfo.objects.first()
    order = invoice.order

    # ルート要素（UBL Invoice準拠）
    root = ET.Element('Invoice')
    root.set('xmlns', 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2')
    root.set('xmlns:cac', 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2')
    root.set('xmlns:cbc', 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2')

    # ─── ヘッダー ───
    ET.SubElement(root, 'cbc:CustomizationID').text = 'urn:peppol:pint:billing-1@jp-1'
    ET.SubElement(root, 'cbc:ProfileID').text = 'urn:peppol:bis:billing'
    ET.SubElement(root, 'cbc:ID').text = invoice.invoice_no
    ET.SubElement(root, 'cbc:IssueDate').text = invoice.issue_date.isoformat()
    ET.SubElement(root, 'cbc:InvoiceTypeCode').text = '380'  # Commercial Invoice
    ET.SubElement(root, 'cbc:DocumentCurrencyCode').text = 'JPY'

    # 対象期間
    period = ET.SubElement(root, 'cac:InvoicePeriod')
    ET.SubElement(period, 'cbc:StartDate').text = invoice.target_month.isoformat()
    # 月末を算出
    import calendar, datetime
    last_day = calendar.monthrange(invoice.target_month.year, invoice.target_month.month)[1]
    end_date = datetime.date(invoice.target_month.year, invoice.target_month.month, last_day)
    ET.SubElement(period, 'cbc:EndDate').text = end_date.isoformat()

    # 注文番号への参照
    order_ref = ET.SubElement(root, 'cac:OrderReference')
    ET.SubElement(order_ref, 'cbc:ID').text = order.order_id

    # ─── 発行者（甲 = 自社） ───
    supplier = ET.SubElement(root, 'cac:AccountingSupplierParty')
    supplier_party = ET.SubElement(supplier, 'cac:Party')
    if company:
        supplier_name = ET.SubElement(supplier_party, 'cac:PartyName')
        ET.SubElement(supplier_name, 'cbc:Name').text = company.name

        postal = ET.SubElement(supplier_party, 'cac:PostalAddress')
        ET.SubElement(postal, 'cbc:PostalZone').text = company.postal_code
        ET.SubElement(postal, 'cbc:StreetName').text = company.address
        country = ET.SubElement(postal, 'cac:Country')
        ET.SubElement(country, 'cbc:IdentificationCode').text = 'JP'

        if company.registration_no:
            tax_scheme = ET.SubElement(supplier_party, 'cac:PartyTaxScheme')
            ET.SubElement(tax_scheme, 'cbc:CompanyID').text = company.registration_no
            scheme = ET.SubElement(tax_scheme, 'cac:TaxScheme')
            ET.SubElement(scheme, 'cbc:ID').text = 'VAT'

        contact = ET.SubElement(supplier_party, 'cac:Contact')
        ET.SubElement(contact, 'cbc:Telephone').text = company.tel

    # ─── 受領者（乙 = パートナー） ───
    customer = ET.SubElement(root, 'cac:AccountingCustomerParty')
    customer_party = ET.SubElement(customer, 'cac:Party')
    partner = order.partner

    cust_name = ET.SubElement(customer_party, 'cac:PartyName')
    ET.SubElement(cust_name, 'cbc:Name').text = partner.name

    cust_postal = ET.SubElement(customer_party, 'cac:PostalAddress')
    ET.SubElement(cust_postal, 'cbc:PostalZone').text = partner.postal_code
    ET.SubElement(cust_postal, 'cbc:StreetName').text = partner.address
    cust_country = ET.SubElement(cust_postal, 'cac:Country')
    ET.SubElement(cust_country, 'cbc:IdentificationCode').text = 'JP'

    # ─── 税額集計 ───
    tax_total = ET.SubElement(root, 'cac:TaxTotal')
    tax_amt = ET.SubElement(tax_total, 'cbc:TaxAmount')
    tax_amt.set('currencyID', 'JPY')
    tax_amt.text = str(invoice.tax_amount)

    tax_subtotal = ET.SubElement(tax_total, 'cac:TaxSubtotal')
    taxable = ET.SubElement(tax_subtotal, 'cbc:TaxableAmount')
    taxable.set('currencyID', 'JPY')
    taxable.text = str(invoice.subtotal_amount)
    tax_sub_amt = ET.SubElement(tax_subtotal, 'cbc:TaxAmount')
    tax_sub_amt.set('currencyID', 'JPY')
    tax_sub_amt.text = str(invoice.tax_amount)

    tax_category = ET.SubElement(tax_subtotal, 'cac:TaxCategory')
    ET.SubElement(tax_category, 'cbc:ID').text = 'S'
    ET.SubElement(tax_category, 'cbc:Percent').text = '10'
    tax_scheme_elem = ET.SubElement(tax_category, 'cac:TaxScheme')
    ET.SubElement(tax_scheme_elem, 'cbc:ID').text = 'VAT'

    # ─── 合計金額 ───
    monetary = ET.SubElement(root, 'cac:LegalMonetaryTotal')
    line_ext = ET.SubElement(monetary, 'cbc:LineExtensionAmount')
    line_ext.set('currencyID', 'JPY')
    line_ext.text = str(invoice.subtotal_amount)

    tax_excl = ET.SubElement(monetary, 'cbc:TaxExclusiveAmount')
    tax_excl.set('currencyID', 'JPY')
    tax_excl.text = str(invoice.subtotal_amount)

    tax_incl = ET.SubElement(monetary, 'cbc:TaxInclusiveAmount')
    tax_incl.set('currencyID', 'JPY')
    tax_incl.text = str(invoice.total_amount)

    payable = ET.SubElement(monetary, 'cbc:PayableAmount')
    payable.set('currencyID', 'JPY')
    payable.text = str(invoice.total_amount)

    # ─── 明細行 ───
    for idx, item in enumerate(invoice.items.all(), start=1):
        inv_line = ET.SubElement(root, 'cac:InvoiceLine')
        ET.SubElement(inv_line, 'cbc:ID').text = str(idx)

        qty = ET.SubElement(inv_line, 'cbc:InvoicedQuantity')
        qty.set('unitCode', 'MON')  # 人月
        qty.text = '1'

        line_amt = ET.SubElement(inv_line, 'cbc:LineExtensionAmount')
        line_amt.set('currencyID', 'JPY')
        line_amt.text = str(item.item_subtotal)

        # 明細の名称
        inv_item = ET.SubElement(inv_line, 'cac:Item')
        ET.SubElement(inv_item, 'cbc:Name').text = item.person_name
        ET.SubElement(inv_item, 'cbc:Description').text = f'SES業務委託 {item.person_name}'

        # 単価
        inv_price = ET.SubElement(inv_line, 'cac:Price')
        price_amt = ET.SubElement(inv_price, 'cbc:PriceAmount')
        price_amt.set('currencyID', 'JPY')
        price_amt.text = str(item.base_fee)

        # 超過金額（AllowanceCharge = charge）
        if item.excess_amount > 0:
            charge = ET.SubElement(inv_line, 'cac:AllowanceCharge')
            ET.SubElement(charge, 'cbc:ChargeIndicator').text = 'true'
            ET.SubElement(charge, 'cbc:AllowanceChargeReason').text = '超過精算'
            charge_amt = ET.SubElement(charge, 'cbc:Amount')
            charge_amt.set('currencyID', 'JPY')
            charge_amt.text = str(item.excess_amount)

        # 控除金額（AllowanceCharge = allowance）
        if item.shortage_amount > 0:
            allowance = ET.SubElement(inv_line, 'cac:AllowanceCharge')
            ET.SubElement(allowance, 'cbc:ChargeIndicator').text = 'false'
            ET.SubElement(allowance, 'cbc:AllowanceChargeReason').text = '控除精算'
            allow_amt = ET.SubElement(allowance, 'cbc:Amount')
            allow_amt.set('currencyID', 'JPY')
            allow_amt.text = str(item.shortage_amount)

        # SES拡張: 実稼働時間・精算条件
        ses_ext = ET.SubElement(inv_item, 'cac:AdditionalItemProperty')
        ET.SubElement(ses_ext, 'cbc:Name').text = 'WorkTime'
        ET.SubElement(ses_ext, 'cbc:Value').text = str(float(item.work_time))

        ses_ext2 = ET.SubElement(inv_item, 'cac:AdditionalItemProperty')
        ET.SubElement(ses_ext2, 'cbc:Name').text = 'TimeLowerLimit'
        ET.SubElement(ses_ext2, 'cbc:Value').text = str(float(item.time_lower_limit))

        ses_ext3 = ET.SubElement(inv_item, 'cac:AdditionalItemProperty')
        ET.SubElement(ses_ext3, 'cbc:Name').text = 'TimeUpperLimit'
        ET.SubElement(ses_ext3, 'cbc:Value').text = str(float(item.time_upper_limit))

    # XML文字列を整形して返す
    xml_str = ET.tostring(root, encoding='unicode', xml_declaration=False)
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='utf-8')

    return pretty_xml
