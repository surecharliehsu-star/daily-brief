from abc import ABC, abstractmethod
from ..models import Paper


class BaseCrawler(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @property
    def default_limit(self) -> int:
        return 200

    @abstractmethod
    def fetch_papers(self, limit: int | None = None) -> list[Paper]:
        pass
