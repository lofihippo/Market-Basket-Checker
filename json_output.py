"""Write complete JSON exports without leaving a partially written result."""
import json
import os
from pathlib import Path
import tempfile


def write_json(path, data):
    """Create parent directories and atomically replace the destination.

    Serialize beside the destination so replacement stays on the same
    filesystem. If serialization or replacement fails, retain the previous
    export and remove the temporary file.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
