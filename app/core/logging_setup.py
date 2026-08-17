from pathlib import Path

from loguru import logger

from app.core.config import settings

# Rotation/retention keep this bounded on a long-running prod process that
# never restarts for weeks — without a cap a busy service would eventually
# fill the shared app_data volume.
_ROTATION = "10 MB"
_RETENTION = 5


def configure_file_logging(service_name: str) -> None:
    """Adds a file sink alongside loguru's existing stderr sink (already
    captured by `docker logs`) — the file sink is what read_logs_tool.py
    reads from, since a container can't see another container's stdout
    without mounting the Docker socket."""
    log_dir = Path(settings.LOG_STORAGE_PATH)
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / f"{service_name}.log",
        rotation=_ROTATION,
        retention=_RETENTION,
        level="INFO",
        enqueue=True,
    )
