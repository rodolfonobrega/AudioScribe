"""Composite output handler that executes every configured handler."""

from typing import Iterable, List

from core.interfaces.output_handler import AbstractOutputHandler


class CompositeOutputHandler(AbstractOutputHandler):
    def __init__(self, handlers: Iterable[AbstractOutputHandler]):
        self.handlers: List[AbstractOutputHandler] = list(handlers)

    def output(self, text: str, **kwargs) -> None:
        errors = []
        for handler in self.handlers:
            try:
                handler.output(text, **kwargs)
            except Exception as exc:
                errors.append(f"{handler.__class__.__name__}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def is_available(self) -> bool:
        return all(handler.is_available() for handler in self.handlers)

    @property
    def platform(self) -> str:
        return self.handlers[0].platform if self.handlers else "unknown"

    @property
    def supported_platforms(self) -> List[str]:
        platforms = set()
        for handler in self.handlers:
            platforms.update(handler.supported_platforms)
        return sorted(platforms)
