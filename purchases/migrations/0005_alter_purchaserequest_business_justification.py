# Generated by Django 5.2.3 on 2025-07-17 11:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchases', '0004_alter_purchaserequestline_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaserequest',
            name='business_justification',
            field=models.TextField(blank=True, help_text='Why is this purchase needed?', null=True, verbose_name='Business Justification'),
        ),
    ]
