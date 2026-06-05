"""Hot-reload ConstraintConfig when SPEC.md is modified on disk."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .parser import ConstraintConfig, load_spec

logger = logging.getLogger(__name__)


class _SpecReloadHandler(FileSystemEventHandler):
    def __init__(self, spec_path: Path, on_reload: Callable[[ConstraintConfig], None]) -> None:
        self._spec_path = spec_path.resolve()
        self._on_reload = on_reload

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if Path(event.src_path).resolve() == self._spec_path:
            logger.info("SPEC.md changed — reloading constraints.")
            try:
                config = load_spec(self._spec_path)
                self._on_reload(config)
                logger.info("Constraints reloaded successfully.")
            except Exception as exc:
                logger.error("Failed to reload SPEC.md: %s", exc)


class SpecWatcher:
    """Watches a SPEC.md file and calls a callback when it changes."""

    def __init__(self, spec_path: str | Path, on_reload: Callable[[ConstraintConfig], None]) -> None:
        self._spec_path = Path(spec_path).resolve()
        self._on_reload = on_reload
        self._observer: Observer | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the filesystem watcher in a daemon thread."""
        with self._lock:
            if self._observer is not None:
                return
            handler = _SpecReloadHandler(self._spec_path, self._on_reload)
            observer = Observer()
            observer.schedule(handler, str(self._spec_path.parent), recursive=False)
            observer.daemon = True
            observer.start()
            self._observer = observer
            logger.info("Watching %s for changes.", self._spec_path)

    def stop(self) -> None:
        """Stop the filesystem watcher."""
        with self._lock:
            if self._observer is None:
                return
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Stopped watching SPEC.md.")
