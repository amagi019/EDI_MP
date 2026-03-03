"""
PaymentTermとContractTermを「パートナー×プロジェクト」構造に変更し、
ProjectにClient FKを追加するカスタムマイグレーション。
"""
from django.db import migrations, models
import django.db.models.deletion


def rebuild_tables(apps, schema_editor):
    from django.db import connection
    cursor = connection.cursor()

    if connection.vendor == 'sqlite':
        cursor.execute("PRAGMA foreign_keys=OFF;")

        # === PaymentTerm テーブルの再構築（Client FK なし） ===
        cursor.execute('DROP TABLE IF EXISTS "orders_paymentterm";')
        cursor.execute("""
            CREATE TABLE "orders_paymentterm" (
                "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                "description" text NOT NULL DEFAULT '',
                "partner_id" varchar(32) NOT NULL REFERENCES "core_customer" ("customer_id") DEFERRABLE INITIALLY DEFERRED,
                "project_id" varchar(50) NOT NULL REFERENCES "orders_project" ("project_id") DEFERRABLE INITIALLY DEFERRED
            );
        """)
        cursor.execute('CREATE INDEX "orders_paymentterm_partner_id" ON "orders_paymentterm" ("partner_id");')
        cursor.execute('CREATE INDEX "orders_paymentterm_project_id" ON "orders_paymentterm" ("project_id");')
        cursor.execute('CREATE UNIQUE INDEX "orders_paymentterm_unique" ON "orders_paymentterm" ("partner_id", "project_id");')

        # === ContractTerm テーブルの再構築（Client FK なし） ===
        cursor.execute('DROP TABLE IF EXISTS "orders_contractterm";')
        cursor.execute("""
            CREATE TABLE "orders_contractterm" (
                "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                "description" text NOT NULL DEFAULT '',
                "partner_id" varchar(32) NOT NULL REFERENCES "core_customer" ("customer_id") DEFERRABLE INITIALLY DEFERRED,
                "project_id" varchar(50) NOT NULL REFERENCES "orders_project" ("project_id") DEFERRABLE INITIALLY DEFERRED
            );
        """)
        cursor.execute('CREATE INDEX "orders_contractterm_partner_id" ON "orders_contractterm" ("partner_id");')
        cursor.execute('CREATE INDEX "orders_contractterm_project_id" ON "orders_contractterm" ("project_id");')
        cursor.execute('CREATE UNIQUE INDEX "orders_contractterm_unique" ON "orders_contractterm" ("partner_id", "project_id");')

        # === Project テーブルに client_id カラムを追加 ===
        cursor.execute('INSERT OR IGNORE INTO "core_client" ("id", "name") VALUES (1, "（未設定）");')
        cursor.execute('ALTER TABLE "orders_project" ADD COLUMN "client_id" bigint NOT NULL DEFAULT 1 REFERENCES "core_client" ("id") DEFERRABLE INITIALLY DEFERRED;')
        cursor.execute('CREATE INDEX "orders_project_client_id" ON "orders_project" ("client_id");')

        cursor.execute("PRAGMA foreign_keys=ON;")
    else:
        # PostgreSQL用
        # PaymentTerm 再構築
        cursor.execute('DROP TABLE IF EXISTS orders_paymentterm CASCADE;')
        cursor.execute("""
            CREATE TABLE orders_paymentterm (
                id SERIAL PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                partner_id VARCHAR(32) NOT NULL REFERENCES core_customer (partner_id) DEFERRABLE INITIALLY DEFERRED,
                project_id VARCHAR(50) NOT NULL REFERENCES orders_project (project_id) DEFERRABLE INITIALLY DEFERRED
            );
        """)
        cursor.execute('CREATE INDEX orders_paymentterm_partner_id ON orders_paymentterm (partner_id);')
        cursor.execute('CREATE INDEX orders_paymentterm_project_id ON orders_paymentterm (project_id);')
        cursor.execute('CREATE UNIQUE INDEX orders_paymentterm_unique ON orders_paymentterm (partner_id, project_id);')

        # ContractTerm 再構築
        cursor.execute('DROP TABLE IF EXISTS orders_contractterm CASCADE;')
        cursor.execute("""
            CREATE TABLE orders_contractterm (
                id SERIAL PRIMARY KEY,
                description TEXT NOT NULL DEFAULT '',
                partner_id VARCHAR(32) NOT NULL REFERENCES core_customer (partner_id) DEFERRABLE INITIALLY DEFERRED,
                project_id VARCHAR(50) NOT NULL REFERENCES orders_project (project_id) DEFERRABLE INITIALLY DEFERRED
            );
        """)
        cursor.execute('CREATE INDEX orders_contractterm_partner_id ON orders_contractterm (partner_id);')
        cursor.execute('CREATE INDEX orders_contractterm_project_id ON orders_contractterm (project_id);')
        cursor.execute('CREATE UNIQUE INDEX orders_contractterm_unique ON orders_contractterm (partner_id, project_id);')

        # Project テーブルに client_id 追加
        cursor.execute("""
            INSERT INTO core_client (id, name, postal_code, address, tel, email, representative_name, registration_no, url, representative_title)
            VALUES (1, '（未設定）', '', '', '', '', '', '', '', '')
            ON CONFLICT (id) DO NOTHING;
        """)
        cursor.execute("ALTER TABLE orders_project ADD COLUMN client_id BIGINT NOT NULL DEFAULT 1 REFERENCES core_client (id) DEFERRABLE INITIALLY DEFERRED;")
        cursor.execute('CREATE INDEX orders_project_client_id ON orders_project (client_id);')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_rename_models'),
        ('orders', '0015_alter_contractterm_id_alter_deliverable_id_and_more'),
    ]

    operations = [
        # DB変更
        migrations.RunPython(rebuild_tables, migrations.RunPython.noop),

        # State同期
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # PaymentTerm: title削除、partner/project FK追加
                migrations.RemoveField(model_name='paymentterm', name='title'),
                migrations.AddField(
                    model_name='paymentterm', name='partner',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.customer', verbose_name='パートナー'),
                    preserve_default=False,
                ),
                migrations.AddField(
                    model_name='paymentterm', name='project',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='orders.project', verbose_name='プロジェクト'),
                    preserve_default=False,
                ),
                migrations.AlterUniqueTogether(
                    name='paymentterm',
                    unique_together={('partner', 'project')},
                ),
                # ContractTerm: description→TextField、partner/project FK追加
                migrations.AlterField(
                    model_name='contractterm', name='description',
                    field=models.TextField(blank=True, verbose_name='説明'),
                ),
                migrations.AddField(
                    model_name='contractterm', name='partner',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.customer', verbose_name='パートナー'),
                    preserve_default=False,
                ),
                migrations.AddField(
                    model_name='contractterm', name='project',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='orders.project', verbose_name='プロジェクト'),
                    preserve_default=False,
                ),
                migrations.AlterUniqueTogether(
                    name='contractterm',
                    unique_together={('partner', 'project')},
                ),
                # Project: customer FK追加 (旧client → core.0020でCustomerにリネーム済み)
                migrations.AddField(
                    model_name='project', name='customer',
                    field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='core.customer', verbose_name='取引先'),
                    preserve_default=False,
                ),
            ],
            database_operations=[],  # DBはRunPythonで変更済み
        ),
    ]
