"""
手動マイグレーション: Client→Customer, Customer→Partner へのリネーム

DBテーブル名はdb_tableで維持するため、Djangoの内部モデル参照のみ変更。
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0019_client_representative_title_and_more'),
    ]

    operations = [
        # 1. Customer → Partner に先にリネーム（衝突回避）
        migrations.RenameModel(
            old_name='Customer',
            new_name='Partner',
        ),
        # 2. Client → Customer にリネーム
        migrations.RenameModel(
            old_name='Client',
            new_name='Customer',
        ),
        # 3. Partner (旧Customer) のフィールド名変更: customer_id → partner_id
        migrations.RenameField(
            model_name='partner',
            old_name='customer_id',
            new_name='partner_id',
        ),
        # 4. Profile のフィールド名変更: customer → partner
        migrations.RenameField(
            model_name='profile',
            old_name='customer',
            new_name='partner',
        ),
        # 5. SentEmailLog のフィールド名変更: customer → partner
        migrations.RenameField(
            model_name='sentemaillog',
            old_name='customer',
            new_name='partner',
        ),
        # 6. MasterContractProgress のフィールド名変更: customer → partner
        migrations.RenameField(
            model_name='mastercontractprogress',
            old_name='customer',
            new_name='partner',
        ),
    ]
