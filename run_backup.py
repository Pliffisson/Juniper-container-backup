#!/usr/bin/env python3
"""
Manual backup execution script.
Runs a single backup job without starting the scheduler.
"""
import sys
import os

# Add src to path
sys.path.insert(0, '/app/src')

from backup import run_backup_job, init_git_repo

if __name__ == "__main__":
    print("🔧 Executing manual backup...")
    try:
        repo = init_git_repo()
        run_backup_job()
        print("✅ Backup completed successfully!")
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        sys.exit(1)
