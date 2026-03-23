"""Internal utilities for the solidmodel_converter package."""

import os
from pathlib import Path

_LOCAL_APPDATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
LOCAL_APPDATA = _LOCAL_APPDATA
APP_CACHE_DIR = _LOCAL_APPDATA / 'modulesgoods' / 'cache'


class _LogBuffer:
    def log(self, category: str, msg: str) -> None:
        print(f'[{category}] {msg}')


log_buffer = _LogBuffer()
