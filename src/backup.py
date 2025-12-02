import os
import datetime
import glob
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
ROUTER_HOSTS = os.getenv("ROUTER_HOSTS", "").split(",")
PORT = os.getenv("PORT", "60002")
USERNAME = os.getenv("JUNIPER_USERNAME")
PASSWORD = os.getenv("JUNIPER_PASSWORD")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/backups")
MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", 10))

def get_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def cleanup_old_backups(hostname):
    """Keeps only the last MAX_BACKUPS files for a given hostname."""
    files = glob.glob(os.path.join(BACKUP_DIR, f"{hostname}_*.conf"))
    files.sort(key=os.path.getmtime)
    
    if len(files) > MAX_BACKUPS:
        files_to_delete = files[:-MAX_BACKUPS]
        for f in files_to_delete:
            try:
                os.remove(f)
                print(f"Deleted old backup: {f}")
            except OSError as e:
                print(f"Error deleting {f}: {e}")

def backup_router(hostname):
    print(f"Starting backup for {hostname}...")
    
    device = {
        "device_type": "juniper_junos",
        "host": hostname.strip(),
        "username": USERNAME,
        "password": PASSWORD,
        "port": PORT,
    }

    try:
        with ConnectHandler(**device) as net_connect:
            print(f"Connected to {hostname}")
            config_output = net_connect.send_command("show configuration | display set")
            
            timestamp = get_timestamp()
            filename = f"{hostname.strip()}_{timestamp}.conf"
            filepath = os.path.join(BACKUP_DIR, filename)
            
            # Ensure backup directory exists
            os.makedirs(BACKUP_DIR, exist_ok=True)
            
            with open(filepath, "w") as f:
                f.write(config_output)
            
            print(f"Backup saved to {filepath}")
            cleanup_old_backups(hostname.strip())
            
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
        print(f"Failed to connect to {hostname}: {e}")
    except Exception as e:
        print(f"An error occurred with {hostname}: {e}")

def main():
    if not ROUTER_HOSTS or ROUTER_HOSTS == ['']:
        print("No routers configured in ROUTER_HOSTS.")
        return

    if not USERNAME or not PASSWORD:
        print("Credentials not found in environment variables.")
        return

    print(f"Starting backup job for {len(ROUTER_HOSTS)} routers.")
    for host in ROUTER_HOSTS:
        if host:
            backup_router(host)
    print("Backup job completed.")

if __name__ == "__main__":
    main()
