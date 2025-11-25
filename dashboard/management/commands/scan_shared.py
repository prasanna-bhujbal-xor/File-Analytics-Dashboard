# dashboard/management/commands/scan_shared.py
from django.core.management.base import BaseCommand
from dashboard.utils import scan_shared_folder
from django.conf import settings

class Command(BaseCommand):
    help = "Scan the shared folder and update FileMetadata (usage: manage.py scan_shared --path D:\\... )"

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, help='Path to shared folder (overrides settings.SHARED_FOLDER_PATH)')
        parser.add_argument('--create-missing', action='store_true', help='Create DB rows for missing files')

    def handle(self, *args, **options):
        path = options.get('path') or getattr(settings, 'SHARED_FOLDER_PATH', None)
        if not path:
            self.stderr.write("Shared folder path not provided. Use --path or set SHARED_FOLDER_PATH in settings.")
            return

        stats = scan_shared_folder(root_path=path, create_missing=options.get('create_missing', False))
        self.stdout.write("Rescan complete. Created: {created}, Updated: {updated}, Deleted: {deleted}".format(**stats))
