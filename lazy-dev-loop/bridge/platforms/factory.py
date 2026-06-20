from platforms.base import PlatformAdapter
from platforms.linux import LinuxPlatform


_platform_instance: PlatformAdapter | None = None


def get_platform() -> PlatformAdapter:
    global _platform_instance
    if _platform_instance is None:
        _platform_instance = LinuxPlatform()
    return _platform_instance
