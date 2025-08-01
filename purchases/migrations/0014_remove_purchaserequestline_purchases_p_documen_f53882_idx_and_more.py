# Generated by Django 5.2.3 on 2025-07-22 14:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchases', '0013_remove_purchaserequestline_estimated_price_and_more'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='purchaserequestline',
            name='purchases_p_documen_f53882_idx',
        ),
        migrations.RemoveIndex(
            model_name='purchaserequestline',
            name='purchases_p_product_918f59_idx',
        ),
        migrations.RemoveIndex(
            model_name='purchaserequestline',
            name='purchases_p_suggest_45b34c_idx',
        ),
        migrations.RemoveField(
            model_name='purchaserequestline',
            name='priority',
        ),
        migrations.RemoveField(
            model_name='purchaserequestline',
            name='suggested_supplier',
        ),
        migrations.AlterField(
            model_name='purchaserequest',
            name='business_justification',
            field=models.TextField(blank=True, help_text='Why is this purchase needed?', null=True, verbose_name='Business Justification'),
        ),
    ]
