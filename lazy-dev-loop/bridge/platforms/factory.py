import platform as _platform

from platforms.base import PlatformAdapter
from platforms.linux import LinuxPlatform
from platforms.windows_wsl import WindowsWSLPlatform


_platform_instance: PlatformAdapter | None = None


def get_platform() -> PlatformAdapter:
    global _platform_instance
    if _platform_instance is None:
        if _platform.system() == "Windows":
            _platform_instance = WindowsWSLPlatform()
        else:
            _platform_instance = LinuxPlatform()
    return _platform_instance
