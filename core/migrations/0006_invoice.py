# Generated migration for Invoice model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_alter_qrstandorder_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='Invoice',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('invoice_number', models.CharField(max_length=50, unique=True)),
                ('pdf_file', models.FileField(blank=True, null=True, upload_to='invoices/')),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('generated_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='invoice', to='core.order')),
            ],
        ),
    ]
