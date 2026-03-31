"""
旧 orders_monthlytask から新 tasks_monthlytask へのデータ移行
"""
from django.db import migrations


def migrate_data_forward(apps, schema_editor):
    """旧テーブルからデータをコピー"""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'orders_monthlytask'
        """)
        if cursor.fetchone()[0] == 0:
            return

        cursor.execute("""
            INSERT INTO tasks_monthlytask (
                partner_id, project_id, work_month, task_type,
                responsible, deadline, status, completed_at,
                note, reminder_sent, alert_sent, deadline_notified,
                created_at, updated_at
            )
            SELECT
                bi.partner_id, bi.project_id, mt.work_month, mt.task_type,
                mt.responsible, mt.deadline, mt.status, mt.completed_at,
                COALESCE('注文書: ' || o.order_id, ''),
                mt.reminder_sent, mt.alert_sent, mt.deadline_notified,
                mt.created_at, mt.updated_at
            FROM orders_monthlytask mt
            JOIN orders_orderbasicinfo bi ON mt.basic_info_id = bi.id
            LEFT JOIN orders_order o ON mt.related_order_id = o.id
            ON CONFLICT DO NOTHING
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0001_initial_monthly_task'),
    ]

    operations = [
        migrations.RunPython(migrate_data_forward, migrations.RunPython.noop),
    ]
