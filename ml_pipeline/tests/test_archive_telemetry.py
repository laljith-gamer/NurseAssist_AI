import os
import sys
import time
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.archive_telemetry import archive_old_telemetry

def test_archive_old_telemetry(tmp_path):
    base_dir = tmp_path
    drop_dir = base_dir / "telemetry_drop"
    archive_dir = base_dir / "archived_logs"
    
    drop_dir.mkdir(parents=True, exist_ok=True)
    
    # Create an old file
    old_file = drop_dir / "old.json"
    old_file.write_text("{}")
    
    # Create a new file
    new_file = drop_dir / "new.json"
    new_file.write_text("{}")
    
    # Modify mtime
    now = time.time()
    os.utime(str(old_file), (now - 100 * 24 * 3600, now - 100 * 24 * 3600))
    os.utime(str(new_file), (now - 10 * 24 * 3600, now - 10 * 24 * 3600))
    
    # Run archiving
    archive_old_telemetry(days=90, base_dir=base_dir)
    
    # Check assertions
    assert not old_file.exists(), "Old file should be moved"
    assert new_file.exists(), "New file should stay"
    assert (archive_dir / "old.json").exists(), "Old file should be in archive"
    assert not (archive_dir / "new.json").exists(), "New file should not be in archive"

