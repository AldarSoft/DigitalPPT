from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """Filesystem storage without a public URL; files are served by authorized views."""

    @property
    def base_location(self):
        return str(Path(settings.PRIVATE_MEDIA_ROOT))

    @property
    def location(self):
        return str(Path(self.base_location).resolve())

    @property
    def base_url(self):
        return None


private_media_storage = PrivateMediaStorage()
