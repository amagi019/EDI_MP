"""
PostgreSQL用: Djangoモデルからテーブルを直接作成するスクリプト。
マイグレーションの不整合を回避するため、migrate --fake の後に実行する。
"""
import os
import sys

# Docker内で実行する場合、/app をモジュール検索パスに追加
sys.path.insert(0, '/app')

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'EDI_MP.settings')
django.setup()

from django.apps import apps
from django.db import connection


def create_tables():
    """登録済みDjangoモデルから、存在しないテーブルを直接作成する"""
    with connection.schema_editor() as schema_editor:
        # 既存テーブルを取得
        existing_tables = set(connection.introspection.table_names())

        for app_config in apps.get_app_configs():
            for model in app_config.get_models():
                table_name = model._meta.db_table
                if table_name not in existing_tables:
                    try:
                        schema_editor.create_model(model)
                        print(f"  Created table: {table_name}")
                    except Exception as e:
                        print(f"  Error creating {table_name}: {e}")
                else:
                    print(f"  Table exists: {table_name}")


if __name__ == '__main__':
    print("Creating tables from Django models...")
    create_tables()
    print("Done.")
