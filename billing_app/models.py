# billing_app/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from decimal import Decimal

class Client(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='clients')
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class ProductService(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products_services')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    # NEW: Tax percentage for this product/service (e.g., 5.00 for 5%)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="e.g., 5.00 for 5%")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def price_with_tax(self):
        # Calculate price including product's specific tax
        tax_multiplier = Decimal(1) + (self.tax_percentage / Decimal(100))
        return (self.price * tax_multiplier).quantize(Decimal('0.01'))


class Bill(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bills')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='bills')
    bill_date = models.DateField()
    due_date = models.DateField()
    # total_amount will now be the total *including* item-specific taxes
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_paid = models.BooleanField(default=False)
    # REMOVED: tax_rate from Bill model to avoid confusion with product-specific tax
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Bill #{self.id} for {self.client.name} on {self.bill_date}"
    
    # Add this method to calculate subtotal
    def calculate_subtotal(self):
        return sum(item.get_total for item in self.items.all()).quantize(Decimal('0.01')) if self.items.exists() else Decimal('0.00')

    @property
    def subtotal_before_all_taxes(self):
        # Sum of item base prices (ProductService.price * quantity)
        return sum(item.product_service.price * item.quantity for item in self.items.all()).quantize(Decimal('0.01')) if self.items.exists() else Decimal('0.00')

    @property
    def total_tax_on_items(self):
        # Sum of tax amounts for each item
        return sum(item.tax_amount_per_item for item in self.items.all()).quantize(Decimal('0.01')) if self.items.exists() else Decimal('0.00')

    # The total_amount property on Bill is now directly calculated from BillItem's item_total
    # (which includes item-specific tax)

class BillItem(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name='items')
    product_service = models.ForeignKey(ProductService, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    # unit_price will now store the price *including* the product's tax
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    # item_total will now store the total for this item, *including* the product's tax
    item_total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total for this item, including product's tax")

    def save(self, *args, **kwargs):
        # Auto-fill unit_price from product's price_with_tax
        self.unit_price = self.product_service.price_with_tax
        self.item_total = (self.quantity * self.unit_price).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    @property
    def get_total(self): # <--- ADDED THIS PROPERTY
        return self.item_total

    @property
    def tax_amount_per_item(self):
        # Calculate the tax amount for this specific item (quantity * tax_per_unit)
        base_unit_price = self.product_service.price
        tax_percentage = self.product_service.tax_percentage
        tax_per_unit = (base_unit_price * (tax_percentage / Decimal(100))).quantize(Decimal('0.01'))
        return (tax_per_unit * self.quantity).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.quantity} x {self.product_service.name} on Bill #{self.bill.id}"

# Signals to update Bill total_amount
@receiver(post_save, sender=BillItem)
@receiver(post_delete, sender=BillItem)
def update_bill_total(sender, instance, **kwargs):
    bill = instance.bill
    # total_amount is now sum of item_total (which already includes item-specific tax)
    # Ensure bill.items.all() is evaluated correctly
    bill_items_sum = sum(item.item_total for item in bill.items.all()).quantize(Decimal('0.01')) if bill.items.exists() else Decimal('0.00')

    # Only save if the total_amount has actually changed to prevent infinite loops
    if bill.total_amount != bill_items_sum:
        bill.total_amount = bill_items_sum
        bill.save(update_fields=['total_amount'])