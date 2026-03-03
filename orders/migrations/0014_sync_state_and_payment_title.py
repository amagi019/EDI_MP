"""
カスタムSQLマイグレーション(0012, 0013)で行ったDB変更を
Djangoのマイグレーション状態に反映させるための状態同期マイグレーション。
加えて、PaymentTermの変更（titleフィールド追加、descriptionのTextField化）も含む。
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0013_master_tables_auto_id'),
    ]

    operations = [
        # === DB変更済みのPK変更をDjangoのマイグレーション状態に反映 ===
        # SeparateDatabaseAndState: state_operationsのみ実行（DBは既に変更済み）
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # Workplace
                migrations.RemoveField(model_name='workplace', name='workplace_id'),
                migrations.AddField(
                    model_name='workplace', name='id',
                    field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
                # Deliverable
                migrations.RemoveField(model_name='deliverable', name='deliverable_id'),
                migrations.AddField(
                    model_name='deliverable', name='id',
                    field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
                # PaymentTerm
                migrations.RemoveField(model_name='paymentterm', name='payment_term_id'),
                migrations.AddField(
                    model_name='paymentterm', name='id',
                    field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
                # ContractTerm
                migrations.RemoveField(model_name='contractterm', name='contract_term_id'),
                migrations.AddField(
                    model_name='contractterm', name='id',
                    field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
                # Product
                migrations.RemoveField(model_name='product', name='product_id'),
                migrations.AddField(
                    model_name='product', name='id',
                    field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
                ),
            ],
            database_operations=[],  # DBは0012, 0013で変更済み
        ),

        # === PaymentTerm: titleフィールド追加（DB実変更あり） ===
        migrations.AddField(
            model_name='paymentterm',
            name='title',
            field=models.CharField(default='', max_length=100, verbose_name='タイトル'),
            preserve_default=False,
        ),
        # === PaymentTerm: descriptionをTextFieldに変更（DB実変更あり） ===
        migrations.AlterField(
            model_name='paymentterm',
            name='description',
            field=models.TextField(blank=True, verbose_name='説明'),
        ),
    ]
