"""
Deliverable, PaymentTerm, ContractTerm, ProductのPKを
CharField(primary_key)からAutoField(自動採番)に変更するカスタムマイグレーション。
OrderテーブルとOrderItemテーブルのFK参照も合わせて再構築する。
PostgreSQLではDROP CASCADE + 再作成で対応。
"""
from django.db import migrations


def rebuild_tables_sqlite(apps, schema_editor):
    """SQLite用のPK変更"""
    from django.db import connection

    if connection.vendor != 'sqlite':
        return

    cursor = connection.cursor()

    # FK制約を無効化
    cursor.execute("PRAGMA foreign_keys=OFF;")

    # === 1. Deliverable テーブルの再構築 ===
    cursor.execute("""
        CREATE TABLE "orders_deliverable_new" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "description" VARCHAR(255) NOT NULL
        );
    """)
    cursor.execute("""
        INSERT INTO "orders_deliverable_new" ("description")
        SELECT "description" FROM "orders_deliverable";
    """)
    cursor.execute('DROP TABLE "orders_deliverable";')
    cursor.execute('ALTER TABLE "orders_deliverable_new" RENAME TO "orders_deliverable";')

    # === 2. PaymentTerm テーブルの再構築 ===
    cursor.execute("""
        CREATE TABLE "orders_paymentterm_new" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "description" VARCHAR(255) NOT NULL
        );
    """)
    cursor.execute("""
        INSERT INTO "orders_paymentterm_new" ("description")
        SELECT "description" FROM "orders_paymentterm";
    """)
    cursor.execute('DROP TABLE "orders_paymentterm";')
    cursor.execute('ALTER TABLE "orders_paymentterm_new" RENAME TO "orders_paymentterm";')

    # === 3. ContractTerm テーブルの再構築 ===
    cursor.execute("""
        CREATE TABLE "orders_contractterm_new" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "description" VARCHAR(255) NOT NULL
        );
    """)
    cursor.execute("""
        INSERT INTO "orders_contractterm_new" ("description")
        SELECT "description" FROM "orders_contractterm";
    """)
    cursor.execute('DROP TABLE "orders_contractterm";')
    cursor.execute('ALTER TABLE "orders_contractterm_new" RENAME TO "orders_contractterm";')

    # === 4. Product テーブルの再構築 ===
    cursor.execute("""
        CREATE TABLE "orders_product_new" (
            "id" INTEGER PRIMARY KEY AUTOINCREMENT,
            "name" VARCHAR(100) NOT NULL,
            "price" integer NOT NULL
        );
    """)
    cursor.execute("""
        INSERT INTO "orders_product_new" ("name", "price")
        SELECT "name", "price" FROM "orders_product";
    """)
    cursor.execute('DROP TABLE "orders_product";')
    cursor.execute('ALTER TABLE "orders_product_new" RENAME TO "orders_product";')

    # === 5. Order テーブルのFK参照を再構築 ===
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
            "contract_term_id" bigint NULL REFERENCES "orders_contractterm" ("id") DEFERRABLE INITIALLY DEFERRED,
            "customer_id" varchar(32) NOT NULL REFERENCES "core_customer" ("customer_id") DEFERRABLE INITIALLY DEFERRED,
            "deliverable_id" bigint NULL REFERENCES "orders_deliverable" ("id") DEFERRABLE INITIALLY DEFERRED,
            "payment_term_id" bigint NULL REFERENCES "orders_paymentterm" ("id") DEFERRABLE INITIALLY DEFERRED,
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
    cursor.execute("""
        INSERT INTO "orders_order_new"
        SELECT * FROM "orders_order";
    """)
    cursor.execute('DROP TABLE "orders_order";')
    cursor.execute('ALTER TABLE "orders_order_new" RENAME TO "orders_order";')

    cursor.execute('CREATE INDEX "orders_order_contract_term_id" ON "orders_order" ("contract_term_id");')
    cursor.execute('CREATE INDEX "orders_order_customer_id" ON "orders_order" ("customer_id");')
    cursor.execute('CREATE INDEX "orders_order_deliverable_id" ON "orders_order" ("deliverable_id");')
    cursor.execute('CREATE INDEX "orders_order_payment_term_id" ON "orders_order" ("payment_term_id");')
    cursor.execute('CREATE INDEX "orders_order_project_id" ON "orders_order" ("project_id");')
    cursor.execute('CREATE INDEX "orders_order_workplace_id" ON "orders_order" ("workplace_id");')

    # === 6. OrderItem テーブルのFK参照を再構築 ===
    cursor.execute("""
        CREATE TABLE "orders_orderitem_new" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "quantity" integer NOT NULL,
            "price" integer NOT NULL,
            "order_id" varchar(20) NOT NULL REFERENCES "orders_order" ("order_id") DEFERRABLE INITIALLY DEFERRED,
            "actual_hours" decimal NOT NULL,
            "base_fee" integer NOT NULL,
            "effort" decimal NOT NULL,
            "excess_rate" integer NOT NULL,
            "person_name" varchar(64) NOT NULL,
            "shortage_rate" integer NOT NULL,
            "time_lower_limit" decimal NOT NULL,
            "time_upper_limit" decimal NOT NULL,
            "product_id" bigint NULL REFERENCES "orders_product" ("id") DEFERRABLE INITIALLY DEFERRED
        );
    """)
    cursor.execute("""
        INSERT INTO "orders_orderitem_new"
        SELECT * FROM "orders_orderitem";
    """)
    cursor.execute('DROP TABLE "orders_orderitem";')
    cursor.execute('ALTER TABLE "orders_orderitem_new" RENAME TO "orders_orderitem";')

    cursor.execute('CREATE INDEX "orders_orderitem_order_id" ON "orders_orderitem" ("order_id");')
    cursor.execute('CREATE INDEX "orders_orderitem_product_id" ON "orders_orderitem" ("product_id");')

    # FK制約を再有効化
    cursor.execute("PRAGMA foreign_keys=ON;")


def rebuild_tables_postgresql(apps, schema_editor):
    """PostgreSQL用: マスタテーブルのPKをCharFieldからAutoFieldに変更"""
    from django.db import connection

    if connection.vendor == 'sqlite':
        return

    cursor = connection.cursor()

    # OrderItem の product FK を削除
    cursor.execute("ALTER TABLE orders_orderitem DROP COLUMN IF EXISTS product_id;")

    # Order の FK を削除
    cursor.execute("ALTER TABLE orders_order DROP COLUMN IF EXISTS contract_term_id;")
    cursor.execute("ALTER TABLE orders_order DROP COLUMN IF EXISTS deliverable_id;")
    cursor.execute("ALTER TABLE orders_order DROP COLUMN IF EXISTS payment_term_id;")

    # マスタテーブルを再作成
    for table, fields in [
        ('orders_deliverable', '"description" VARCHAR(255) NOT NULL'),
        ('orders_paymentterm', '"description" VARCHAR(255) NOT NULL'),
        ('orders_contractterm', '"description" VARCHAR(255) NOT NULL'),
        ('orders_product', '"name" VARCHAR(100) NOT NULL, "price" INTEGER NOT NULL'),
    ]:
        cursor.execute(f'DROP TABLE IF EXISTS {table} CASCADE;')
        cursor.execute(f'CREATE TABLE {table} (id SERIAL PRIMARY KEY, {fields});')

    # Order にFK を re-add (integer)
    cursor.execute("""
        ALTER TABLE orders_order
            ADD COLUMN contract_term_id BIGINT NULL REFERENCES orders_contractterm(id) DEFERRABLE INITIALLY DEFERRED,
            ADD COLUMN deliverable_id BIGINT NULL REFERENCES orders_deliverable(id) DEFERRABLE INITIALLY DEFERRED,
            ADD COLUMN payment_term_id BIGINT NULL REFERENCES orders_paymentterm(id) DEFERRABLE INITIALLY DEFERRED;
    """)
    cursor.execute("CREATE INDEX orders_order_contract_term_id ON orders_order (contract_term_id);")
    cursor.execute("CREATE INDEX orders_order_deliverable_id ON orders_order (deliverable_id);")
    cursor.execute("CREATE INDEX orders_order_payment_term_id ON orders_order (payment_term_id);")

    # OrderItem にproduct FK を re-add
    cursor.execute("""
        ALTER TABLE orders_orderitem
            ADD COLUMN product_id BIGINT NULL REFERENCES orders_product(id) DEFERRABLE INITIALLY DEFERRED;
    """)
    cursor.execute("CREATE INDEX orders_orderitem_product_id ON orders_orderitem (product_id);")


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0012_workplace_auto_id'),
    ]

    operations = [
        migrations.RunPython(rebuild_tables_sqlite, migrations.RunPython.noop),
        migrations.RunPython(rebuild_tables_postgresql, migrations.RunPython.noop),
    ]
