import os
import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class TasksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tasks'
    verbose_name = _('タスク管理')

    def ready(self):
        """アプリ起動時にリマインドスケジューラを起動する"""
        import sys

        # manage.py コマンドがcollectstaticやmigrate等の場合はスキップ
        if len(sys.argv) > 1 and sys.argv[1] in ('collectstatic', 'migrate', 'makemigrations', 'shell', 'test'):
            return

        # runserver のリロード時の二重起動を防止
        # Gunicornでは RUN_MAIN が設定されないので常に起動
        run_main = os.environ.get('RUN_MAIN')
        if run_main == 'true' or run_main is None:
            try:
                from tasks.scheduler import start_scheduler
                start_scheduler()
                logger.info('[TasksConfig] スケジューラを起動しました')
            except Exception as e:
                logger.warning(f'[TasksConfig] スケジューラ起動に失敗: {e}')
