# Generated by Django 5.2.3 on 2025-07-15 17:11

import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('inventory', '0001_initial'),
        ('nomenclatures', '0002_pricegroup'),
        ('partners', '0001_initial'),
        ('products', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Unique code like REQ, ORD, DEL, INV', max_length=10, unique=True, verbose_name='Code')),
                ('name', models.CharField(help_text='Human readable name', max_length=100, verbose_name='Name')),
                ('description', models.TextField(blank=True, help_text='Detailed description of this document type', verbose_name='Description')),
                ('type_key', models.CharField(choices=[('request', 'Request'), ('order', 'Order'), ('delivery', 'Delivery'), ('invoice', 'Invoice'), ('adjustment', 'Adjustment'), ('transfer', 'Transfer'), ('stock_out', 'Stock Out')], help_text='Classification of document behavior', max_length=20, verbose_name='Type Key')),
                ('stock_effect', models.IntegerField(choices=[(1, 'Increases stock'), (-1, 'Decreases stock'), (0, 'No effect')], default=0, help_text='How this document type affects inventory levels', verbose_name='Stock Effect')),
                ('allow_reverse_operations', models.BooleanField(default=False, help_text='Allow negative quantities to reverse the stock effect', verbose_name='Allow Reverse Operations')),
                ('can_be_source', models.BooleanField(default=False, help_text='Whether this document type can be source for other documents', verbose_name='Can Be Source')),
                ('can_reference_multiple_sources', models.BooleanField(default=False, help_text='Whether this document can be created from multiple source documents', verbose_name='Can Reference Multiple Sources')),
                ('auto_confirm', models.BooleanField(default=False, help_text='Automatically confirm document upon creation', verbose_name='Auto Confirm')),
                ('auto_receive', models.BooleanField(default=False, help_text='Automatically mark as received when confirmed', verbose_name='Auto Receive')),
                ('requires_batch', models.BooleanField(default=False, help_text='Whether batch numbers are required for products', verbose_name='Requires Batch')),
                ('requires_expiry', models.BooleanField(default=False, help_text='Whether expiry dates are required for products', verbose_name='Requires Expiry')),
                ('requires_quality_check', models.BooleanField(default=False, help_text='Whether quality approval is required', verbose_name='Requires Quality Check')),
                ('is_system_type', models.BooleanField(default=False, help_text='System-defined type that cannot be deleted', verbose_name='System Type')),
                ('is_active', models.BooleanField(default=True, help_text='Whether this document type is available for use', verbose_name='Active')),
                ('sort_order', models.PositiveIntegerField(default=10, help_text='Order for displaying in lists', verbose_name='Sort Order')),
            ],
            options={
                'verbose_name': 'Document Type',
                'verbose_name_plural': 'Document Types',
                'ordering': ['sort_order', 'name'],
                'indexes': [models.Index(fields=['code'], name='purchases_d_code_a37814_idx'), models.Index(fields=['type_key'], name='purchases_d_type_ke_d0be0c_idx'), models.Index(fields=['is_active'], name='purchases_d_is_acti_b2d25c_idx')],
            },
        ),
        migrations.CreateModel(
            name='PurchaseOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_number', models.CharField(help_text='Auto-generated unique document number', max_length=50, unique=True, verbose_name='Document Number')),
                ('document_date', models.DateField(default=django.utils.timezone.now, help_text='Date when document was created', verbose_name='Document Date')),
                ('external_reference', models.CharField(blank=True, help_text='PO number, contract reference, etc.', max_length=100, verbose_name='External Reference')),
                ('notes', models.TextField(blank=True, help_text='Additional notes and comments', verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('subtotal', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Sum of all line totals before VAT', max_digits=12, verbose_name='Subtotal')),
                ('discount_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total discount amount', max_digits=12, verbose_name='Total Discount')),
                ('vat_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total VAT amount', max_digits=12, verbose_name='VAT Total')),
                ('grand_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Final total including VAT', max_digits=12, verbose_name='Grand Total')),
                ('is_paid', models.BooleanField(default=False, help_text='Whether this document has been paid', verbose_name='Is Paid')),
                ('payment_date', models.DateField(blank=True, help_text='When payment was made', null=True, verbose_name='Payment Date')),
                ('payment_method', models.CharField(blank=True, help_text='How payment was made', max_length=50, verbose_name='Payment Method')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('sent', 'Sent to Supplier'), ('confirmed', 'Confirmed by Supplier'), ('in_delivery', 'In Delivery'), ('received', 'Received'), ('cancelled', 'Cancelled'), ('closed', 'Closed')], default='draft', max_length=20, verbose_name='Status')),
                ('expected_delivery_date', models.DateField(help_text='When we expect to receive this order', verbose_name='Expected Delivery Date')),
                ('requested_delivery_date', models.DateField(blank=True, help_text='When we requested delivery from supplier', null=True, verbose_name='Requested Delivery Date')),
                ('is_urgent', models.BooleanField(default=False, help_text='Whether this is an urgent/emergency order', verbose_name='Urgent Order')),
                ('order_method', models.CharField(blank=True, help_text='How this order was placed (phone, email, system, etc.)', max_length=50, verbose_name='Order Method')),
                ('delivery_terms', models.CharField(blank=True, help_text='Delivery terms (FOB, CIF, etc.)', max_length=100, verbose_name='Delivery Terms')),
                ('special_conditions', models.TextField(blank=True, help_text='Any special conditions or requirements', verbose_name='Special Conditions')),
                ('payment_terms', models.CharField(blank=True, help_text='Payment terms for this order', max_length=100, verbose_name='Payment Terms')),
                ('supplier_confirmed', models.BooleanField(default=False, help_text='Whether supplier has confirmed this order', verbose_name='Supplier Confirmed')),
                ('supplier_confirmed_date', models.DateField(blank=True, help_text='When supplier confirmed the order', null=True, verbose_name='Supplier Confirmed Date')),
                ('supplier_order_reference', models.CharField(blank=True, help_text="Supplier's reference number for this order", max_length=100, verbose_name='Supplier Order Reference')),
                ('supplier_contact_person', models.CharField(blank=True, help_text='Contact person at supplier for this order', max_length=100, verbose_name='Supplier Contact Person')),
                ('supplier_contact_phone', models.CharField(blank=True, help_text='Phone number for order-related contact', max_length=20, verbose_name='Supplier Contact Phone')),
                ('supplier_contact_email', models.EmailField(blank=True, help_text='Email for order-related contact', max_length=254, verbose_name='Supplier Contact Email')),
                ('sent_to_supplier_at', models.DateTimeField(blank=True, help_text='When order was sent to supplier', null=True, verbose_name='Sent to Supplier At')),
                ('delivery_status', models.CharField(choices=[('pending', 'Pending'), ('partial', 'Partially Delivered'), ('completed', 'Fully Delivered'), ('cancelled', 'Cancelled')], default='pending', help_text='Current delivery status of this order', max_length=20, verbose_name='Delivery Status')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='created_%(class)s_documents', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('location', models.ForeignKey(help_text='Business location', on_delete=django.db.models.deletion.PROTECT, to='inventory.inventorylocation', verbose_name='Location')),
                ('sent_by', models.ForeignKey(blank=True, help_text='User who sent the order to supplier', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sent_purchase_orders', to=settings.AUTH_USER_MODEL, verbose_name='Sent By')),
                ('supplier', models.ForeignKey(help_text='The supplier for this document', on_delete=django.db.models.deletion.PROTECT, to='partners.supplier', verbose_name='Supplier')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='updated_%(class)s_documents', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
            options={
                'verbose_name': 'Purchase Order',
                'verbose_name_plural': 'Purchase Orders',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DeliveryReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_number', models.CharField(help_text='Auto-generated unique document number', max_length=50, unique=True, verbose_name='Document Number')),
                ('document_date', models.DateField(default=django.utils.timezone.now, help_text='Date when document was created', verbose_name='Document Date')),
                ('external_reference', models.CharField(blank=True, help_text='PO number, contract reference, etc.', max_length=100, verbose_name='External Reference')),
                ('notes', models.TextField(blank=True, help_text='Additional notes and comments', verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('subtotal', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Sum of all line totals before VAT', max_digits=12, verbose_name='Subtotal')),
                ('discount_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total discount amount', max_digits=12, verbose_name='Total Discount')),
                ('vat_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total VAT amount', max_digits=12, verbose_name='VAT Total')),
                ('grand_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Final total including VAT', max_digits=12, verbose_name='Grand Total')),
                ('is_paid', models.BooleanField(default=False, help_text='Whether this document has been paid', verbose_name='Is Paid')),
                ('payment_date', models.DateField(blank=True, help_text='When payment was made', null=True, verbose_name='Payment Date')),
                ('payment_method', models.CharField(blank=True, help_text='How payment was made', max_length=50, verbose_name='Payment Method')),
                ('delivery_date', models.DateField(help_text='When goods were delivered', verbose_name='Delivery Date')),
                ('delivery_instructions', models.TextField(blank=True, help_text='Special instructions for delivery', verbose_name='Delivery Instructions')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('delivered', 'Delivered (Arrived)'), ('received', 'Received (Checked)'), ('processed', 'Processed (Inventory Updated)'), ('completed', 'Completed'), ('cancelled', 'Cancelled')], default='draft', max_length=20, verbose_name='Status')),
                ('creation_type', models.CharField(choices=[('from_orders', 'From Purchase Orders'), ('direct', 'Direct Delivery')], default='from_orders', help_text='How this delivery was created', max_length=20, verbose_name='Creation Type')),
                ('delivery_note_number', models.CharField(blank=True, help_text="Supplier's delivery note number", max_length=50, verbose_name='Delivery Note Number')),
                ('driver_name', models.CharField(blank=True, help_text='Name of delivery driver', max_length=100, verbose_name='Driver Name')),
                ('driver_phone', models.CharField(blank=True, help_text='Driver contact number', max_length=20, verbose_name='Driver Phone')),
                ('vehicle_info', models.CharField(blank=True, help_text='Vehicle license plate, type, etc.', max_length=100, verbose_name='Vehicle Info')),
                ('received_at', models.DateTimeField(blank=True, help_text='When delivery was received and checked', null=True, verbose_name='Received At')),
                ('processed_at', models.DateTimeField(blank=True, help_text='When delivery was fully processed', null=True, verbose_name='Processed At')),
                ('quality_checked', models.BooleanField(default=False, help_text='Whether quality control was performed', verbose_name='Quality Checked')),
                ('quality_approved', models.BooleanField(default=True, help_text='Whether delivery passed quality control', verbose_name='Quality Approved')),
                ('has_quality_issues', models.BooleanField(default=False, help_text='Whether there are quality problems with this delivery', verbose_name='Has Quality Issues')),
                ('quality_notes', models.TextField(blank=True, help_text='Quality control notes and observations', verbose_name='Quality Notes')),
                ('has_variances', models.BooleanField(default=False, help_text='Whether there are quantity/price variances', verbose_name='Has Variances')),
                ('variance_notes', models.TextField(blank=True, help_text='Notes about variances found', verbose_name='Variance Notes')),
                ('special_handling_notes', models.TextField(blank=True, help_text='Special handling requirements or observations', verbose_name='Special Handling Notes')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='created_%(class)s_documents', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('location', models.ForeignKey(help_text='Business location', on_delete=django.db.models.deletion.PROTECT, to='inventory.inventorylocation', verbose_name='Location')),
                ('processed_by', models.ForeignKey(blank=True, help_text='Who processed this delivery', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='processed_deliveries', to=settings.AUTH_USER_MODEL, verbose_name='Processed By')),
                ('quality_inspector', models.ForeignKey(blank=True, help_text='Who performed quality inspection', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='quality_inspected_deliveries', to=settings.AUTH_USER_MODEL, verbose_name='Quality Inspector')),
                ('received_by', models.ForeignKey(blank=True, help_text='Who received this delivery', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='received_deliveries', to=settings.AUTH_USER_MODEL, verbose_name='Received By')),
                ('supplier', models.ForeignKey(help_text='The supplier for this document', on_delete=django.db.models.deletion.PROTECT, to='partners.supplier', verbose_name='Supplier')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='updated_%(class)s_documents', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
                ('source_orders', models.ManyToManyField(blank=True, help_text='Purchase orders fulfilled by this delivery', related_name='deliveries', to='purchases.purchaseorder', verbose_name='Source Orders')),
            ],
            options={
                'verbose_name': 'Delivery Receipt',
                'verbose_name_plural': 'Delivery Receipts',
                'ordering': ['-delivery_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PurchaseOrderLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line_number', models.PositiveIntegerField(help_text='Sequential line number within document', verbose_name='Line Number')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Quantity in specified unit', max_digits=10, verbose_name='Quantity')),
                ('unit_price', models.DecimalField(decimal_places=4, default=Decimal('0.0000'), help_text='Price per unit', max_digits=10, verbose_name='Unit Price')),
                ('discount_percent', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Discount percentage', max_digits=5, verbose_name='Discount %')),
                ('line_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total amount for this line', max_digits=12, verbose_name='Line Total')),
                ('ordered_quantity', models.DecimalField(decimal_places=3, help_text='Quantity ordered from supplier', max_digits=10, verbose_name='Ordered Quantity')),
                ('confirmed_quantity', models.DecimalField(blank=True, decimal_places=3, help_text='Quantity confirmed by supplier (if different from ordered)', max_digits=10, null=True, verbose_name='Confirmed Quantity')),
                ('delivered_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), help_text='Total quantity already delivered', max_digits=10, verbose_name='Delivered Quantity')),
                ('remaining_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), help_text='Quantity still to be delivered', max_digits=10, verbose_name='Remaining Quantity')),
                ('delivery_status', models.CharField(choices=[('pending', 'Pending'), ('partial', 'Partially Delivered'), ('completed', 'Fully Delivered'), ('cancelled', 'Cancelled')], default='pending', help_text='Delivery status for this line', max_length=20, verbose_name='Delivery Status')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='purchases.purchaseorder', verbose_name='Purchase Order')),
                ('product', models.ForeignKey(help_text='Product being purchased', on_delete=django.db.models.deletion.PROTECT, to='products.product', verbose_name='Product')),
                ('unit', models.ForeignKey(help_text='Unit of measure for this line', on_delete=django.db.models.deletion.PROTECT, to='nomenclatures.unitofmeasure', verbose_name='Unit')),
            ],
            options={
                'verbose_name': 'Purchase Order Line',
                'verbose_name_plural': 'Purchase Order Lines',
                'ordering': ['document', 'line_number'],
            },
        ),
        migrations.CreateModel(
            name='DeliveryLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line_number', models.PositiveIntegerField(help_text='Sequential line number within document', verbose_name='Line Number')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Quantity in specified unit', max_digits=10, verbose_name='Quantity')),
                ('unit_price', models.DecimalField(decimal_places=4, default=Decimal('0.0000'), help_text='Price per unit', max_digits=10, verbose_name='Unit Price')),
                ('discount_percent', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Discount percentage', max_digits=5, verbose_name='Discount %')),
                ('line_total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Total amount for this line', max_digits=12, verbose_name='Line Total')),
                ('ordered_quantity', models.DecimalField(blank=True, decimal_places=3, help_text='Quantity that was originally ordered', max_digits=10, null=True, verbose_name='Ordered Quantity')),
                ('received_quantity', models.DecimalField(decimal_places=3, help_text='Quantity actually received', max_digits=10, verbose_name='Received Quantity')),
                ('variance_quantity', models.DecimalField(decimal_places=3, default=Decimal('0.000'), help_text='Difference between ordered and received (received - ordered)', max_digits=10, verbose_name='Variance Quantity')),
                ('quality_approved', models.BooleanField(default=True, help_text='Whether this item passed quality control', verbose_name='Quality Approved')),
                ('quality_issue_type', models.CharField(blank=True, choices=[('damaged', 'Damaged'), ('expired', 'Expired'), ('wrong_product', 'Wrong Product'), ('poor_quality', 'Poor Quality'), ('contaminated', 'Contaminated'), ('packaging_issue', 'Packaging Issue'), ('other', 'Other')], help_text='Type of quality issue (if any)', max_length=20, verbose_name='Quality Issue Type')),
                ('quality_notes', models.TextField(blank=True, help_text='Quality control notes for this item', verbose_name='Quality Notes')),
                ('batch_number', models.CharField(blank=True, help_text='Batch/lot number from supplier', max_length=50, verbose_name='Batch Number')),
                ('expiry_date', models.DateField(blank=True, help_text='Product expiry date', null=True, verbose_name='Expiry Date')),
                ('production_date', models.DateField(blank=True, help_text='Product production date', null=True, verbose_name='Production Date')),
                ('requires_special_handling', models.BooleanField(default=False, help_text='Whether this item needs special handling', verbose_name='Requires Special Handling')),
                ('temperature_at_receipt', models.DecimalField(blank=True, decimal_places=2, help_text='Temperature when received (for cold chain tracking)', max_digits=5, null=True, verbose_name='Temperature at Receipt')),
                ('product', models.ForeignKey(help_text='Product being purchased', on_delete=django.db.models.deletion.PROTECT, to='products.product', verbose_name='Product')),
                ('unit', models.ForeignKey(help_text='Unit of measure for this line', on_delete=django.db.models.deletion.PROTECT, to='nomenclatures.unitofmeasure', verbose_name='Unit')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='purchases.deliveryreceipt', verbose_name='Delivery Receipt')),
                ('source_order_line', models.ForeignKey(blank=True, help_text='Order line this delivery line fulfills (if any)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='delivery_lines', to='purchases.purchaseorderline', verbose_name='Source Order Line')),
            ],
            options={
                'verbose_name': 'Delivery Line',
                'verbose_name_plural': 'Delivery Lines',
                'ordering': ['document', 'line_number'],
            },
        ),
        migrations.CreateModel(
            name='PurchaseRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_number', models.CharField(help_text='Auto-generated unique document number', max_length=50, unique=True, verbose_name='Document Number')),
                ('document_date', models.DateField(default=django.utils.timezone.now, help_text='Date when document was created', verbose_name='Document Date')),
                ('external_reference', models.CharField(blank=True, help_text='PO number, contract reference, etc.', max_length=100, verbose_name='External Reference')),
                ('notes', models.TextField(blank=True, help_text='Additional notes and comments', verbose_name='Notes')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('submitted', 'Submitted for Approval'), ('approved', 'Approved'), ('rejected', 'Rejected'), ('converted', 'Converted to Order'), ('cancelled', 'Cancelled')], default='draft', max_length=20, verbose_name='Status')),
                ('request_type', models.CharField(choices=[('regular', 'Regular Purchase'), ('urgent', 'Urgent Purchase'), ('emergency', 'Emergency Purchase'), ('consumables', 'Consumables Restock'), ('maintenance', 'Maintenance Supplies'), ('project', 'Project Materials')], default='regular', help_text='Type of purchase request', max_length=20, verbose_name='Request Type')),
                ('urgency_level', models.CharField(choices=[('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('critical', 'Critical')], default='normal', help_text='How urgent is this request', max_length=10, verbose_name='Urgency Level')),
                ('business_justification', models.TextField(help_text='Why is this purchase needed?', verbose_name='Business Justification')),
                ('expected_usage', models.TextField(blank=True, help_text='How will these items be used?', verbose_name='Expected Usage')),
                ('approval_required', models.BooleanField(default=True, help_text='Does this request need approval?', verbose_name='Approval Required')),
                ('approved_at', models.DateTimeField(blank=True, null=True, verbose_name='Approved At')),
                ('rejection_reason', models.TextField(blank=True, help_text='Why was this request rejected?', verbose_name='Rejection Reason')),
                ('converted_at', models.DateTimeField(blank=True, null=True, verbose_name='Converted At')),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='purchase_requests_approved', to=settings.AUTH_USER_MODEL, verbose_name='Approved By')),
                ('converted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='purchase_requests_converted', to=settings.AUTH_USER_MODEL, verbose_name='Converted By')),
                ('converted_to_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='converted_from_request', to='purchases.purchaseorder', verbose_name='Converted to Order')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='created_%(class)s_documents', to=settings.AUTH_USER_MODEL, verbose_name='Created By')),
                ('location', models.ForeignKey(help_text='Business location', on_delete=django.db.models.deletion.PROTECT, to='inventory.inventorylocation', verbose_name='Location')),
                ('requested_by', models.ForeignKey(help_text='Person who made the request', on_delete=django.db.models.deletion.PROTECT, related_name='purchase_requests_made', to=settings.AUTH_USER_MODEL, verbose_name='Requested By')),
                ('supplier', models.ForeignKey(help_text='The supplier for this document', on_delete=django.db.models.deletion.PROTECT, to='partners.supplier', verbose_name='Supplier')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='updated_%(class)s_documents', to=settings.AUTH_USER_MODEL, verbose_name='Updated By')),
            ],
            options={
                'verbose_name': 'Purchase Request',
                'verbose_name_plural': 'Purchase Requests',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='source_request',
            field=models.ForeignKey(blank=True, help_text='Request this order was created from (if any)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='generated_orders', to='purchases.purchaserequest', verbose_name='Source Request'),
        ),
        migrations.CreateModel(
            name='PurchaseRequestLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('line_number', models.PositiveIntegerField(help_text='Sequential line number within document', verbose_name='Line Number')),
                ('quantity', models.DecimalField(decimal_places=3, help_text='Quantity in specified unit', max_digits=10, verbose_name='Quantity')),
                ('requested_quantity', models.DecimalField(decimal_places=3, help_text='Quantity requested', max_digits=10, verbose_name='Requested Quantity')),
                ('estimated_price', models.DecimalField(blank=True, decimal_places=4, help_text='Estimated price per unit (optional)', max_digits=10, null=True, verbose_name='Estimated Price')),
                ('item_justification', models.TextField(blank=True, help_text='Why is this specific item needed?', verbose_name='Item Justification')),
                ('priority', models.IntegerField(default=0, help_text='Priority within this request (higher = more important)', verbose_name='Priority')),
                ('quality_notes', models.TextField(blank=True, help_text='Quality requirements or notes', verbose_name='Quality Notes')),
                ('document', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lines', to='purchases.purchaserequest', verbose_name='Purchase Request')),
                ('product', models.ForeignKey(help_text='Product being purchased', on_delete=django.db.models.deletion.PROTECT, to='products.product', verbose_name='Product')),
                ('suggested_supplier', models.ForeignKey(blank=True, help_text='Preferred supplier for this item', null=True, on_delete=django.db.models.deletion.SET_NULL, to='partners.supplier', verbose_name='Suggested Supplier')),
                ('unit', models.ForeignKey(help_text='Unit of measure for this line', on_delete=django.db.models.deletion.PROTECT, to='nomenclatures.unitofmeasure', verbose_name='Unit')),
            ],
            options={
                'verbose_name': 'Purchase Request Line',
                'verbose_name_plural': 'Purchase Request Lines',
                'ordering': ['document', 'line_number'],
            },
        ),
        migrations.AddField(
            model_name='purchaseorderline',
            name='source_request_line',
            field=models.ForeignKey(blank=True, help_text='Request line this order line was created from (if any)', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_lines', to='purchases.purchaserequestline', verbose_name='Source Request Line'),
        ),
        migrations.AddIndex(
            model_name='deliveryreceipt',
            index=models.Index(fields=['status', 'delivery_date'], name='purchases_d_status_d58c24_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryreceipt',
            index=models.Index(fields=['supplier', 'delivery_date'], name='purchases_d_supplie_a39903_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryreceipt',
            index=models.Index(fields=['creation_type', 'status'], name='purchases_d_creatio_d6b17d_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryreceipt',
            index=models.Index(fields=['has_quality_issues', 'quality_checked'], name='purchases_d_has_qua_00ed64_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryreceipt',
            index=models.Index(fields=['has_variances', 'status'], name='purchases_d_has_var_d14a16_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryreceipt',
            index=models.Index(fields=['received_by', '-received_at'], name='purchases_d_receive_d116c8_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['document', 'line_number'], name='purchases_d_documen_031364_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['product'], name='purchases_d_product_57edd9_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['source_order_line'], name='purchases_d_source__5f6594_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['quality_approved', 'batch_number'], name='purchases_d_quality_327512_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['expiry_date'], name='purchases_d_expiry__36960a_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['variance_quantity'], name='purchases_d_varianc_3b78db_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='deliveryline',
            unique_together={('document', 'line_number')},
        ),
        migrations.AddIndex(
            model_name='purchaserequest',
            index=models.Index(fields=['status', 'urgency_level'], name='purchases_p_status_4ce46a_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequest',
            index=models.Index(fields=['requested_by', '-created_at'], name='purchases_p_request_869bd1_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequest',
            index=models.Index(fields=['approved_by', '-approved_at'], name='purchases_p_approve_30a0f7_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequest',
            index=models.Index(fields=['request_type', 'urgency_level'], name='purchases_p_request_cb6533_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['status', 'supplier_confirmed'], name='purchases_p_status_81c61e_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['supplier', 'expected_delivery_date'], name='purchases_p_supplie_03ca62_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['is_urgent', 'status'], name='purchases_p_is_urge_7c5c52_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['delivery_status', 'expected_delivery_date'], name='purchases_p_deliver_d0bdbd_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorder',
            index=models.Index(fields=['source_request'], name='purchases_p_source__2efefc_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequestline',
            index=models.Index(fields=['document', 'line_number'], name='purchases_p_documen_f53882_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequestline',
            index=models.Index(fields=['product'], name='purchases_p_product_918f59_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequestline',
            index=models.Index(fields=['suggested_supplier'], name='purchases_p_suggest_45b34c_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequestline',
            index=models.Index(fields=['priority'], name='purchases_p_priorit_4307dd_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='purchaserequestline',
            unique_together={('document', 'line_number')},
        ),
        migrations.AddIndex(
            model_name='purchaseorderline',
            index=models.Index(fields=['document', 'line_number'], name='purchases_p_documen_63f32e_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderline',
            index=models.Index(fields=['product'], name='purchases_p_product_052d2c_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderline',
            index=models.Index(fields=['source_request_line'], name='purchases_p_source__4a4166_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaseorderline',
            index=models.Index(fields=['delivery_status'], name='purchases_p_deliver_23b15c_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='purchaseorderline',
            unique_together={('document', 'line_number')},
        ),
    ]
