# Generated by Django 5.1.6 on 2025-02-16 16:21

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0009_product_status'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='variant',
            name='image',
        ),
        migrations.RemoveField(
            model_name='variant',
            name='price',
        ),
        migrations.RemoveField(
            model_name='variant',
            name='quantity',
        ),
    ]
