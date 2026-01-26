# Generated manually for KYC, Subscription, and QR Stand Order features

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_order_reject_reason_alter_order_status'),
    ]

    operations = [
        # Add KYC fields to User model
        migrations.AddField(
            model_name='user',
            name='kyc_status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                default='pending',
                max_length=20
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='kyc_reject_reason',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='kyc_document_type',
            field=models.CharField(
                blank=True,
                choices=[('aadhaar', 'Aadhaar Card'), ('food_license', 'Food License')],
                max_length=20,
                null=True
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='kyc_document_file',
            field=models.FileField(blank=True, null=True, upload_to='kyc_documents/'),
        ),
        # Add Subscription fields to User model
        migrations.AddField(
            model_name='user',
            name='subscription_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='subscription_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        # Add new fields to SuperSetting model
        migrations.AddField(
            model_name='supersetting',
            name='per_qr_stand_price',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='supersetting',
            name='subscription_fee_per_month',
            field=models.PositiveIntegerField(default=0),
        ),
        # Create QRStandOrder model
        migrations.CreateModel(
            name='QRStandOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.PositiveIntegerField()),
                ('total_price', models.DecimalField(decimal_places=2, max_digits=12)),
                ('order_status', models.CharField(
                    choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('saved', 'Saved'), ('delivered', 'Delivered')],
                    default='pending',
                    max_length=20
                )),
                ('payment_status', models.CharField(
                    choices=[('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed')],
                    default='pending',
                    max_length=20
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('vendor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='qr_stand_orders',
                    to='core.user'
                )),
            ],
        ),
        # Make TransactionHistory.order nullable for subscription payments
        migrations.AlterField(
            model_name='transactionhistory',
            name='order',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='transactions',
                to='core.order'
            ),
        ),
    ]
