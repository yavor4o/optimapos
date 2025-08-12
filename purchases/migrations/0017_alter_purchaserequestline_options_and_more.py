# purchases/migrations/0017_FIXED.py
# ПОПРАВЕНА ВЕРСИЯ БЕЗ default=1 за DateTimeField

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone  # Добавяме timezone


class Migration(migrations.Migration):
    dependencies = [
        ('nomenclatures', '0016_remove_documenttype_auto_approve_conditions_and_more'),
        ('partners', '0002_alter_customer_price_group'),
        ('products', '0002_remove_product_current_avg_cost_and_more'),
        ('purchases', '0016_remove_deliveryline_serial_numbers_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Първо махаме старите полета
        migrations.RemoveField(
            model_name='deliveryline',
            name='ordered_quantity',
        ),
        migrations.RemoveField(
            model_name='deliveryline',
            name='quantity',
        ),
        migrations.RemoveField(
            model_name='purchaseorderline',
            name='quantity',
        ),
        migrations.RemoveField(
            model_name='purchaseorderline',
            name='remaining_quantity',
        ),
        migrations.RemoveField(
            model_name='purchaserequestline',
            name='quantity',
        ),

        # Добавяме нови полета с правилни defaults
        migrations.AddField(
            model_name='deliveryline',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=timezone.now  # Правилен default за DateTimeField
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='deliveryline',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),

        migrations.AddField(
            model_name='purchaseorderline',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=timezone.now  # Правилен default
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='purchaseorderline',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),

        migrations.AddField(
            model_name='purchaserequestline',
            name='created_at',
            field=models.DateTimeField(
                auto_now_add=True,
                default=timezone.now  # Правилен default
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='purchaserequestline',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),

        # Quantity полета
        migrations.AddField(
            model_name='deliveryline',
            name='expected_quantity',
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text='Expected quantity (from order or manual)',
                max_digits=10,
                null=True,
                verbose_name='Expected Quantity'
            ),
        ),



        migrations.AddField(
            model_name='purchaserequestline',
            name='estimated_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Estimated price per unit (optional, for budgeting)',
                max_digits=10,
                null=True,
                verbose_name='Estimated Unit Price'
            ),
        ),




        # Други промени...
        migrations.AlterField(
            model_name='deliveryline',
            name='variance_quantity',
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal('0.000'),
                editable=False,
                help_text='received - expected (auto-calculated)',
                max_digits=10,
                verbose_name='Variance'
            ),
        ),

        # Indexes
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['batch_number'], name='purchases_d_batch_n_fb4cf6_idx'),
        ),
        migrations.AddIndex(
            model_name='deliveryline',
            index=models.Index(fields=['quality_approved'], name='purchases_d_quality_477e72_idx'),
        ),
        migrations.AddIndex(
            model_name='purchaserequestline',
            index=models.Index(fields=['priority'], name='purchases_p_priorit_4307dd_idx'),
        ),
    ]