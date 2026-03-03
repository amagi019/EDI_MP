"""
手動マイグレーション: Order.partnerのdb_column設定を反映
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0019_rename_fields'),
        ('core', '0021_remaining_fixes'),
    ]

    operations = [
        # Order.partner: db_column='customer_id'を設定
        migrations.AlterField(
            model_name='order',
            name='partner',
            field=models.ForeignKey(
                db_column='customer_id',
                on_delete=django.db.models.deletion.CASCADE,
                to='core.partner',
                verbose_name='パートナー'
            ),
        ),
    ]
