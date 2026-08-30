"""Upload validation rules."""

from pathlib import Path

ALLOWED_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain"},
}


def validate_upload_metadata(filename: str | None, content_type: str | None) -> tuple[str, str]:
    """Validate and normalize an uploaded filename, extension, and MIME type."""
    if not filename:
        raise ValueError("A filename is required")
    safe_name = Path(filename).name
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_TYPES:
        raise ValueError("Only PDF and TXT files are supported")
    if content_type not in ALLOWED_TYPES[extension]:
        raise ValueError("The file MIME type does not match its extension")
    return safe_name, extension


def validate_file_header(extension: str, first_chunk: bytes) -> None:
    """Reject empty files and obvious content-type mismatches."""
    if not first_chunk:
        raise ValueError("The uploaded file is empty")
    if extension == ".pdf" and not first_chunk.startswith(b"%PDF-"):
        raise ValueError("The uploaded file is not a valid PDF")
    if extension == ".txt" and b"\x00" in first_chunk:
        raise ValueError("The uploaded TXT file appears to contain binary data")
