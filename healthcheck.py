#!/usr/bin/env python3
"""
Healthcheck script for Docker container.
Verifies that the backup process is running and responsive.
"""
import os
import sys
import time


def check_health():
    """
    Performs health checks on the backup container.
    
    Returns:
        bool: True if healthy, False otherwise
    """
    # Check 1: Verify backup directory exists and is writable
    try:
        if not os.path.exists('/backups'):
            print("ERROR: Backup directory /backups does not exist", file=sys.stderr)
            return False
        
        # Test write access
        test_file = '/backups/.healthcheck'
        with open(test_file, 'w') as f:
            f.write('ok')
        os.remove(test_file)
    except Exception as e:
        print(f"ERROR: Backup directory not writable: {e}", file=sys.stderr)
        return False
    
    # Check 2: Verify last run timestamp is recent
    # If the process hasn't run in 2x the configured interval, something is wrong
    last_run_file = '/tmp/last_run'
    
    if os.path.exists(last_run_file):
        try:
            last_run_time = os.path.getmtime(last_run_file)
            current_time = time.time()
            elapsed = current_time - last_run_time
            
            # Get configured interval (default 60 minutes)
            interval_minutes = int(os.getenv('BACKUP_INTERVAL_MINUTES', '60'))
            
            # If BACKUP_TIME is set, we run once per day, so allow 25 hours
            if os.getenv('BACKUP_TIME'):
                max_elapsed = 25 * 60 * 60  # 25 hours
            else:
                # Allow 2x the interval before marking unhealthy
                max_elapsed = interval_minutes * 60 * 2
            
            if elapsed > max_elapsed:
                print(f"WARNING: Last run was {elapsed/3600:.1f} hours ago (max: {max_elapsed/3600:.1f}h)", file=sys.stderr)
                return False
                
        except Exception as e:
            print(f"ERROR: Could not check last run time: {e}", file=sys.stderr)
            return False
    else:
        # On first startup, last_run won't exist yet - that's OK
        # We'll only fail if the file exists but is too old
        pass
    
    # All checks passed
    return True


if __name__ == '__main__':
    is_healthy = check_health()
    
    if is_healthy:
        print("OK: Container is healthy")
        sys.exit(0)
    else:
        print("FAIL: Container is unhealthy")
        sys.exit(1)
