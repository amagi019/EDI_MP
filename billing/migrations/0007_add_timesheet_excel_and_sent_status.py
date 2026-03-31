"""
StaffTimesheetにExcelファイル保存フィールドと送付済みステータスを追加
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0006_add_address2_settlement_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='stafftimesheet',
            name='excel_file',
            field=models.FileField(
                blank=True, null=True,
                help_text='アップロードされた稼働報告Excelファイルの原本',
                upload_to='timesheets/excel/',
                verbose_name='Excelファイル',
            ),
        ),
        migrations.AddField(
            model_name='stafftimesheet',
            name='original_filename',
            field=models.CharField(
                blank=True, max_length=512,
                verbose_name='元ファイル名',
            ),
        ),
        migrations.AlterField(
            model_name='stafftimesheet',
            name='status',
            field=models.CharField(
                choices=[
                    ('DRAFT', '下書き'),
                    ('SUBMITTED', '提出済'),
                    ('SENT', '送付済'),
                    ('APPROVED', '承認済'),
                ],
                default='DRAFT', max_length=10,
                verbose_name='ステータス',
            ),
        ),
    ]
