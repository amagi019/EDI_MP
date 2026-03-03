"""
勤務場所IDをCharField(primary_key)からAutoField(自動採番)に変更するカスタムマイグレーション。
SQLiteではFK参照先のPK変更時にcheck_constraintsで失敗するため、
OrderテーブルのFK参照も合わせてテーブルを再構築する。
PostgreSQLではDjango標準のAlterFieldを使用。
"""
from django.db import migrations


def rebuild_tables_sqlite(apps, schema_editor):
    """SQLite用: WorkplaceテーブルのPKをCharFieldからAutoFieldに変更し、
    OrderテーブルのFK参照も合わせて再構築する"""
    from django.db import connection

    if connection.vendor != 'sqlite':
        return

    cursor = connection.cursor()

    # FK制約を無効化
    cursor.execute("PRAGMA foreign_keys=OFF;")

    # === 1. Workplaceテーブルの再構築 ===
    cursor.execute("""
        CREATE TABLE "orders_workplace_new" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "name" VARCHAR(100) NOT NULL,
            "address" VARCHAR(255) NOT NULL DEFAULT ''
        );
    """)
    cursor.execute("""
        INSERT INTO "orders_workplace_new" ("name", "address")
        SELECT "name", "address" FROM "orders_workplace";
    """)
    cursor.execute('DROP TABLE "orders_workplace";')
    cursor.execute('ALTER TABLE "orders_workplace_new" RENAME TO "orders_workplace";')

    # === 2. OrderテーブルのFK参照を再構築 ===
    # workplace_id varchar(50) → workplace_id integer (NULLable) に変更
    cursor.execute("""
        CREATE TABLE "orders_order_new" (
            "order_id" varchar(20) NOT NULL PRIMARY KEY,
            "order_end_ym" date NOT NULL,
            "order_date" date NOT NULL,
            "work_start" date NOT NULL,
            "work_end" date NOT NULL,
            "base_fee" integer NOT NULL,
            "shortage_fee" integer NOT NULL,
            "created_at" datetime NOT NULL,
            "updated_at" datetime NOT NULL,
            "contract_term_id" varchar(50) NULL REFERENCES "orders_contractterm" ("contract_term_id") DEFERRABLE INITIALLY DEFERRED,
            "customer_id" varchar(32) NOT NULL REFERENCES "core_customer" ("customer_id") DEFERRABLE INITIALLY DEFERRED,
            "deliverable_id" varchar(50) NULL REFERENCES "orders_deliverable" ("deliverable_id") DEFERRABLE INITIALLY DEFERRED,
            "payment_term_id" varchar(50) NULL REFERENCES "orders_paymentterm" ("payment_term_id") DEFERRABLE INITIALLY DEFERRED,
            "project_id" varchar(50) NOT NULL REFERENCES "orders_project" ("project_id") DEFERRABLE INITIALLY DEFERRED,
            "workplace_id" bigint NULL REFERENCES "orders_workplace" ("id") DEFERRABLE INITIALLY DEFERRED,
            "excess_fee" integer NOT NULL,
            "remarks" text NOT NULL,
            "time_lower_limit" decimal NOT NULL,
            "time_upper_limit" decimal NOT NULL,
            "contract_items" text NOT NULL,
            "deliverable_text" varchar(255) NOT NULL,
            "payment_condition" text NOT NULL,
            "乙_担当者" varchar(64) NOT NULL,
            "乙_責任者" varchar(64) NOT NULL,
            "作業責任者" varchar(64) NOT NULL,
            "甲_担当者" varchar(64) NOT NULL,
            "甲_責任者" varchar(64) NOT NULL,
            "document_hash" varchar(64) NOT NULL,
            "finalized_at" datetime NULL,
            "acceptance_pdf" varchar(100) NULL,
            "order_pdf" varchar(100) NULL,
            "external_signature_id" varchar(100) NULL,
            "status" varchar(20) NOT NULL
        );
    """)

    # 既存Orderデータをコピー（workplace_idはNULLのままコピー）
    cursor.execute("""
        INSERT INTO "orders_order_new"
        SELECT * FROM "orders_order";
    """)

    cursor.execute('DROP TABLE "orders_order";')
    cursor.execute('ALTER TABLE "orders_order_new" RENAME TO "orders_order";')

    # インデックスの再作成
    cursor.execute('CREATE INDEX "orders_order_contract_term_id" ON "orders_order" ("contract_term_id");')
    cursor.execute('CREATE INDEX "orders_order_customer_id" ON "orders_order" ("customer_id");')
    cursor.execute('CREATE INDEX "orders_order_deliverable_id" ON "orders_order" ("deliverable_id");')
    cursor.execute('CREATE INDEX "orders_order_payment_term_id" ON "orders_order" ("payment_term_id");')
    cursor.execute('CREATE INDEX "orders_order_project_id" ON "orders_order" ("project_id");')
    cursor.execute('CREATE INDEX "orders_order_workplace_id" ON "orders_order" ("workplace_id");')

    # FK制約を再有効化
    cursor.execute("PRAGMA foreign_keys=ON;")


def rebuild_tables_postgresql(apps, schema_editor):
    """PostgreSQL用: WorkplaceテーブルのPKをCharFieldからAutoFieldに変更"""
    from django.db import connection

    if connection.vendor == 'sqlite':
        return

    cursor = connection.cursor()

    # OrderテーブルのFK制約を一時的に削除
    cursor.execute("""
        ALTER TABLE orders_order DROP CONSTRAINT IF EXISTS orders_order_workplace_id_fkey;
    """)
    # workplace_id を DROP (varchar FK)
    cursor.execute("""
        ALTER TABLE orders_order DROP COLUMN IF EXISTS workplace_id;
    """)

    # Workplaceテーブルを再作成
    cursor.execute('DROP TABLE IF EXISTS orders_workplace CASCADE;')
    cursor.execute("""
        CREATE TABLE orders_workplace (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            address VARCHAR(255) NOT NULL DEFAULT ''
        );
    """)

    # Orderテーブルにworkplace_id (integer FK) を追加
    cursor.execute("""
        ALTER TABLE orders_order ADD COLUMN workplace_id BIGINT NULL
            REFERENCES orders_workplace(id) DEFERRABLE INITIALLY DEFERRED;
    """)
    cursor.execute("""
        CREATE INDEX orders_order_workplace_id ON orders_order (workplace_id);
    """)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0011_orderitem_actual_hours_orderitem_base_fee_and_more'),
    ]

    operations = [
        migrations.RunPython(rebuild_tables_sqlite, migrations.RunPython.noop),
        migrations.RunPython(rebuild_tables_postgresql, migrations.RunPython.noop),
    ]
