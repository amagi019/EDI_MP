"""
手動マイグレーション: 残りのdb_tableとカラム名の整合性修正

1. core: Customer/Partnerのdb_table設定を反映
2. orders: Order.customer_id → partner_id カラム名変更
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_rename_models'),
    ]

    operations = [
        # AlterModelTable は不要（db_table はRenameModel後も元のテーブル名を維持するため
        # models.pyのMeta.db_tableと一致させる）

        # Profile.partner: verbose_name更新
        migrations.AlterField(
            model_name='profile',
            name='partner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.partner', verbose_name='パートナー'),
        ),
        # SentEmailLog.partner: verbose_name更新
        migrations.AlterField(
            model_name='sentemaillog',
            name='partner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_logs', to='core.partner', verbose_name='パートナー'),
        ),
        # MasterContractProgress.partner: verbose_name更新
        migrations.AlterField(
            model_name='mastercontractprogress',
            name='partner',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='contract_progress', to='core.partner', verbose_name='パートナー'),
        ),
        # db_table設定をマイグレーション状態に反映
        migrations.AlterModelTable(
            name='customer',
            table='core_client',
        ),
        migrations.AlterModelTable(
            name='partner',
            table='core_customer',
        ),
    ]
