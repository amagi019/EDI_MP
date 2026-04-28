"""
Fernet 暗号化鍵を生成するコマンド。

Usage:
    python manage.py generate_encryption_key

生成された鍵を .env の FILE_ENCRYPTION_KEY に設定してください。
"""

from django.core.management.base import BaseCommand
from cryptography.fernet import Fernet


class Command(BaseCommand):
    help = 'ファイル暗号化用の Fernet 鍵を生成します'

    def handle(self, *args, **options):
        key = Fernet.generate_key().decode()
        self.stdout.write('')
        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS('新しい暗号化鍵を生成しました:'))
        self.stdout.write('')
        self.stdout.write(f'  {key}')
        self.stdout.write('')
        self.stdout.write('.env ファイルに以下を追加してください:')
        self.stdout.write(f'  FILE_ENCRYPTION_KEY={key}')
        self.stdout.write('=' * 60)
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            '⚠ この鍵を紛失すると暗号化済みファイルを復号できなくなります。'
        ))
        self.stdout.write(self.style.WARNING(
            '  必ず安全な場所にバックアップしてください。'
        ))
