# billing_app/forms.py
from django import forms
from django.forms.models import inlineformset_factory
from .models import Client, ProductService, Bill, BillItem
import datetime
from django.core.exceptions import ValidationError

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'address']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class ProductServiceForm(forms.ModelForm):
    class Meta:
        model = ProductService
        fields = ['name', 'description', 'price', 'tax_percentage'] # Added tax_percentage
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            # NEW: Widget for tax_percentage
            'tax_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
        }

class BillForm(forms.ModelForm):
    bill_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        initial=datetime.date.today,
        label="Bill Date"
    )

    class Meta:
        model = Bill
        fields = ['client', 'bill_date', 'due_date', 'is_paid']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}), # Already required
            'is_paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class BillItemForm(forms.ModelForm):
    product_service_name = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control product-autocomplete', 'placeholder': 'Start typing product name'})
    )

    class Meta:
        model = BillItem
        fields = ['product_service', 'quantity']
        widgets = {
            'product_service': forms.HiddenInput(),
            'quantity': forms.NumberInput(attrs={'class': 'form-control item-quantity', 'min': 1}),
        }

# --- Custom Formset for Bill Items Validation ---
class BaseBillItemFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        # Check if any form in the formset has valid data and is not marked for deletion
        # This will count both existing items and newly added ones
        has_items = False
        for form in self.forms:
            if not hasattr(form, 'cleaned_data'): # Skip forms that failed initial validation
                continue
            # If the form has data for product_service and is not marked for deletion
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
                # We also need to check if product_service is actually selected
                # since product_service_name is not bound directly to the model field
                if form.cleaned_data.get('product_service'):
                    has_items = True
                    break

        if not has_items:
            raise ValidationError("You must add at least one product or service to the bill.")


# This is crucial for handling multiple BillItems in a single Bill form
BillItemFormSet = inlineformset_factory(
    Bill,
    BillItem,
    form=BillItemForm,
    formset=BaseBillItemFormSet, # Use our custom formset class
    extra=1,
    can_delete=True,
    fields=['product_service', 'quantity'],
)