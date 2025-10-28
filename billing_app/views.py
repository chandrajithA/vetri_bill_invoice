from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.forms import inlineformset_factory
from django.db.models import Sum
from datetime import datetime
import json
from django.conf import settings
from decimal import Decimal # Import Decimal

from django.conf import settings
from django.contrib.staticfiles import finders
import os

# For reports
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from xhtml2pdf import pisa  # Make sure to install xhtml2pdf: pip install xhtml2pdf
import csv
from django.db.models.functions import TruncMonth # For analytics

from .models import Client, ProductService, Bill, BillItem
from .forms import ClientForm, ProductServiceForm, BillForm, BillItemFormSet

@login_required
def dashboard_view(request):
    # Basic counts
    total_clients = Client.objects.count()
    total_products = ProductService.objects.count()
    total_bills = Bill.objects.count()
    unpaid_bills_count = Bill.objects.filter(is_paid=False).count()

    # Monthly Income Analytics
    monthly_income_data = Bill.objects.filter( is_paid=True) \
        .annotate(month=TruncMonth('bill_date')) \
        .values('month') \
        .annotate(total_income=Sum('total_amount')) \
        .order_by('month')

    months = [item['month'].strftime('%Y-%m') for item in monthly_income_data]
    incomes = [float(item['total_income']) for item in monthly_income_data]

    chart_data = {
        'labels': [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in months],
        'data': incomes,
    }

    context = {
        'total_clients': total_clients,
        'total_products': total_products,
        'total_bills': total_bills,
        'unpaid_bills_count': unpaid_bills_count,
        'chart_data_json': json.dumps(chart_data), # Pass as JSON string
    }
    return render(request, 'billing_app/dashboard.html', context)

# --- Client Views ---
@login_required
def client_list(request):
    clients = Client.objects.order_by('-created_at')
    return render(request, 'billing_app/client_list.html', {'clients': clients})

@login_required
def client_create(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.user = request.user
            client.save()
            return redirect('client_list')
    else:
        form = ClientForm()
    return render(request, 'billing_app/client_form.html', {'form': form, 'title': 'Create Client'})

@login_required
def client_update(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            return redirect('client_list')
    else:
        form = ClientForm(instance=client)
    return render(request, 'billing_app/client_form.html', {'form': form, 'title': 'Update Client'})

@login_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        client.delete()
        return redirect('client_list')
    return render(request, 'billing_app/client_confirm_delete.html', {'client': client})

# --- Product/Service Views ---
@login_required
def product_list(request):
    products = ProductService.objects.order_by('name')
    return render(request, 'billing_app/product_list.html', {'products': products})

@login_required
def product_create(request):
    if request.method == 'POST':
        form = ProductServiceForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.user = request.user
            product.save()
            return redirect('product_list')
    else:
        form = ProductServiceForm()
    return render(request, 'billing_app/product_form.html', {'form': form, 'title': 'Create Product'})

@login_required
def product_update(request, pk):
    product = get_object_or_404(ProductService, pk=pk)
    if request.method == 'POST':
        form = ProductServiceForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect('product_list')
    else:
        form = ProductServiceForm(instance=product)
    return render(request, 'billing_app/product_form.html', {'form': form, 'title': 'Update Product'})

@login_required
def product_delete(request, pk):
    product = get_object_or_404(ProductService, pk=pk)
    product.delete()
    return redirect('product_list')

# --- Bill Views (Most Complex) ---
@login_required
def bill_list(request):
    bills = Bill.objects.order_by('-bill_date', '-created_at')
    return render(request, 'billing_app/bill_list.html', {'bills': bills})

@login_required
def bill_detail(request, pk):
    bill = get_object_or_404(Bill.objects.prefetch_related('items__product_service'), pk=pk)
    return render(request, 'billing_app/bill_detail.html', {'bill': bill})

# Helper function to serialize Decimal objects to strings
def decimal_to_str_serializer(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

@login_required
def bill_create(request):
    bill_form = BillForm()
    formset = BillItemFormSet(queryset=BillItem.objects.none(), prefix='items')

    # Fetch products and convert Decimal fields to strings for JSON serialization
    products_queryset = ProductService.objects.values('id', 'name', 'price', 'tax_percentage')
    products_data = []
    for p in products_queryset:
        products_data.append({
            'id': p['id'],
            'name': p['name'],
            'price': str(p['price']), # Convert Decimal to string
            'tax_percentage': str(p['tax_percentage']), # Convert Decimal to string
        })
    products_json = json.dumps(products_data) # Serialize the list with stringified Decimals

    if request.method == 'POST':
        bill_form = BillForm(request.POST)
        formset = BillItemFormSet(request.POST, prefix='items')

        if bill_form.is_valid() and formset.is_valid():
            bill = bill_form.save(commit=False)
            bill.user = request.user
            bill.save()

            instances = formset.save(commit=False)
            for instance in instances:
                instance.bill = bill
                instance.save()

            for form in formset.deleted_forms:
                form.instance.delete()

            return redirect('bill_detail', pk=bill.pk)
    
    context = {
        'form': bill_form,
        'formset': formset,
        'title': 'Create New Bill',
        'products_json': products_json,
    }
    return render(request, 'billing_app/bill_form.html', context)

@login_required
def bill_update(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    bill_form = BillForm(instance=bill)
    formset = BillItemFormSet(instance=bill, prefix='items')

    # Fetch products and convert Decimal fields to strings for JSON serialization
    products_queryset = ProductService.objects.values('id', 'name', 'price', 'tax_percentage')
    products_data = []
    for p in products_queryset:
        products_data.append({
            'id': p['id'],
            'name': p['name'],
            'price': str(p['price']), # Convert Decimal to string
            'tax_percentage': str(p['tax_percentage']), # Convert Decimal to string
        })
    products_json = json.dumps(products_data) # Serialize the list with stringified Decimals

    if request.method == 'POST':
        bill_form = BillForm(request.POST, instance=bill)
        formset = BillItemFormSet(request.POST, instance=bill, prefix='items')

        if bill_form.is_valid() and formset.is_valid():
            bill = bill_form.save(commit=False)
            bill.user = request.user
            bill.save()

            instances = formset.save(commit=False)
            for instance in instances:
                instance.bill = bill
                instance.save()

            for form in formset.deleted_forms:
                form.instance.delete()

            return redirect('bill_detail', pk=bill.pk)

    context = {
        'form': bill_form,
        'formset': formset,
        'title': f'Update Bill #{bill.id}',
        'products_json': products_json,
        'bill': bill,
    }
    return render(request, 'billing_app/bill_form.html', context)

@login_required
def bill_delete(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    bill.delete()
    return redirect('bill_list')


def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access them.
    """
    result = finders.find(uri)
    if result:
        path = os.path.realpath(result)
    else:
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
    return path

from django.templatetags.static import static
import os
# --- Report Generation ---
@login_required
def generate_bill_pdf(request, pk):
    bill = get_object_or_404(Bill.objects.prefetch_related('items__product_service'), pk=pk)
    template_path = 'billing_app/pdf_bill_template.html'

    context = {'bill': bill, 'font_path': os.path.join(settings.STATIC_ROOT, 'font', 'NotoSans-Regular.ttf'),}

    template = get_template(template_path)
    html = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Invoice_No-{bill.id}.pdf"'

    if pisa.CreatePDF(html, dest=response, link_callback=link_callback).err:
         return HttpResponse('We had some errors <pre>' + html + '</pre>')
    return response




@login_required
def download_bills_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bills_report.csv"'

    writer = csv.writer(response)
    # Header for effective tax rate
    writer.writerow(['Bill ID', 'Client Name', 'Bill Date', 'Due Date', 'Subtotal (base)', 'Tax (%)', 'Tax Amount', 'Total Bill Amount', 'Is Paid', 'Created At'])

    bills = Bill.objects.order_by('-bill_date').prefetch_related('items', 'items__product_service')
    for bill in bills:
        subtotal_before_tax = bill.subtotal_before_all_taxes
        total_tax = bill.total_tax_on_items
        
        effective_tax_rate = Decimal('0.00')
        if subtotal_before_tax > Decimal('0.00'):
            effective_tax_rate = (total_tax / subtotal_before_tax * Decimal(100)).quantize(Decimal('0.01'))

        writer.writerow([
            bill.id,
            bill.client.name,
            bill.bill_date.strftime('%Y-%m-%d'),
            bill.due_date.strftime('%Y-%m-%d') if bill.due_date else '',
            float(subtotal_before_tax),
            float(effective_tax_rate), # The calculated effective tax rate
            float(bill.total_tax_on_items), 
            float(bill.total_amount),
            'Yes' if bill.is_paid else 'No',
            bill.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])

    return response

@login_required
def product_autocomplete(request):
    if 'term' in request.GET:
        qs = ProductService.objects.filter( name__icontains=request.GET.get('term'))
        products = [{'id': p.id, 'label': p.name, 'value': p.name, 'price': float(p.price)} for p in qs]
        return JsonResponse(products, safe=False)
    return JsonResponse([], safe=False)