"""Safe uploaded-file naming and removal helpers."""

from pathlib import Path
from uuid import uuid4


def create_stored_filename(extension: str) -> str:
    """Create an unpredictable storage name while retaining the validated extension."""
    return f"{uuid4().hex}{extension}"


def remove_file(path: Path) -> None:
    """Remove a stored file if it exists."""
    path.unlink(missing_ok=True)
