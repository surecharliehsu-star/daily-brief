from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Paper:
    title: str
    authors: list[str]
    published: str
    series: str
    abstract: str
    pdf_url: str
    source: str
    url: str
    topics: list[str] = field(default_factory=list)
    title_zh: str = ""
    is_monetary: bool = False
    date_estimated: bool = False
    crawled_at: str = ""
    abstract_missing_reason: str = ""

    def to_dict(self) -> dict:
        d = {}
        for f in self.__dataclass_fields__:
            v = getattr(self, f)
            if isinstance(v, list):
                d[f] = list(v)
            else:
                d[f] = v
        return d
