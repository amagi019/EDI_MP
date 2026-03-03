"""
手動マイグレーション: orders側のFK参照をリネームに対応させる

core.Client → core.Customer, core.Customer → core.Partner への対応。
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0018_order_drive_file_id'),
        ('core', '0020_rename_models'),
    ]

    operations = [
        # Project.customer: FK先をcore.Customerに明示的に設定
        migrations.AlterField(
            model_name='project',
            name='customer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.customer', verbose_name='取引先'),
        ),
        # OrderBasicInfo (Order): customer → partner (FK先: core.Partner = 旧Customer)
        migrations.RenameField(
            model_name='orderbasicinfo',
            old_name='customer',
            new_name='partner',
        ),
        # OrderBasicInfo.partner: FK先をcore.Partnerに明示的に設定
        migrations.AlterField(
            model_name='orderbasicinfo',
            name='partner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.partner', verbose_name='パートナー'),
        ),
        # PaymentTerm: FK先をcore.Partnerに変更
        migrations.AlterField(
            model_name='paymentterm',
            name='partner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.partner', verbose_name='パートナー'),
        ),
        # ContractTerm: FK先をcore.Partnerに変更
        migrations.AlterField(
            model_name='contractterm',
            name='partner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.partner', verbose_name='パートナー'),
        ),
        # Person: FK先をcore.Partnerに変更
        migrations.AlterField(
            model_name='person',
            name='partner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.partner', verbose_name='パートナー'),
        ),
    ]
