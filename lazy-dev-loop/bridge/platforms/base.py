from abc import ABC, abstractmethod
import subprocess


class PlatformAdapter(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def run(self, command: str, *, timeout: int | None = None, **kwargs) -> subprocess.CompletedProcess:
        ...

    @abstractmethod
    def popen(self, command: str, **kwargs) -> subprocess.Popen:
        ...

    @abstractmethod
    def check_command(self, command: str) -> bool:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def open_terminal(self, session_name: str) -> dict:
        ...

    @abstractmethod
    def to_exec_path(self, host_path: str) -> str:
        ...

    @abstractmethod
    def to_host_path(self, exec_path: str) -> str:
        ...

    @property
    @abstractmethod
    def env_not_found_message(self) -> str:
        ...
