"""
billing プレゼンテーション層 - Django Admin設定
"""
from django.contrib import admin
from billing.domain.models import (
    BillingCustomer, BillingProduct, BillingInvoice, BillingItem,
)


class BillingItemInline(admin.TabularInline):
    model = BillingItem
    extra = 1
    fields = ['product_name', 'unit_price', 'man_month', 'tax_category', 'sort_order']


@admin.register(BillingCustomer)
class BillingCustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'email', 'phone']
    search_fields = ['name', 'contact_person']


@admin.register(BillingProduct)
class BillingProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'unit_price', 'unit', 'tax_category']
    list_filter = ['tax_category']
    search_fields = ['name']


@admin.register(BillingInvoice)
class BillingInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'issue_date', 'due_date', 'status', 'total']
    list_filter = ['status', 'issue_date']
    search_fields = ['customer__name', 'subject']
    inlines = [BillingItemInline]
    readonly_fields = ['created_at', 'updated_at']

    def total(self, obj):
        return f"¥{obj.total:,}"
    total.short_description = '税込合計'
