# Generated by Django 5.2.3 on 2025-07-22 14:06

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [


        ('partners', '0002_alter_customer_price_group'),
        ('products', '0001_initial'),
        ('purchases', '0014_remove_purchaserequestline_purchases_p_documen_f53882_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaserequestline',
            name='priority',
            field=models.IntegerField(default=0, help_text='Priority within this request (higher = more important)', verbose_name='Priority'),
        ),
        migrations.AddField(
            model_name='purchaserequestline',
            name='suggested_supplier',
            field=models.ForeignKey(blank=True, help_text='Preferred supplier for this item', null=True, on_delete=django.db.models.deletion.SET_NULL, to='partners.supplier', verbose_name='Suggested Supplier'),
        ),
        migrations.AlterField(
            model_name='purchaserequest',
            name='business_justification',
            field=models.TextField(blank=True, default=1, help_text='Why is this purchase needed?', verbose_name='Business Justification'),
            preserve_default=False,
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
    ]
