# billing_app/admin.py

from django.contrib import admin
from .models import Client, ProductService, Bill, BillItem

admin.site.register(Client)
admin.site.register(ProductService)
admin.site.register(Bill)
admin.site.register(BillItem)