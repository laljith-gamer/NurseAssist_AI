"""Archive old telemetry data to prevent unbounded growth."""

import os
import shutil
import time
from pathlib import Path

def archive_old_telemetry(days: int = 90, base_dir: Path | None = None):
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent.parent
    drop_dir = base_dir / "telemetry_drop"
    archive_dir = base_dir / "archived_logs"
    
    if not drop_dir.exists():
        print(f"Directory {drop_dir} does not exist. Nothing to archive.")
        return

    archive_dir.mkdir(parents=True, exist_ok=True)

    cutoff_time = time.time() - (days * 24 * 60 * 60)
    
    count = 0
    for filepath in drop_dir.glob("*.json"):
        if filepath.stat().st_mtime < cutoff_time:
            shutil.move(str(filepath), str(archive_dir / filepath.name))
            count += 1
            
    print(f"Archived {count} telemetry files older than {days} days.")

if __name__ == "__main__":
    archive_old_telemetry()
