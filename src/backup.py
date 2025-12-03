import os
import datetime
import glob
import requests
from git import Repo, InvalidGitRepositoryError
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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def get_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def send_telegram_notification(message):
    """Sends a notification to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured. Skipping notification.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Telegram notification sent.")
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")

def init_git_repo():
    """Initializes a git repository in the backup directory if it doesn't exist."""
    try:
        repo = Repo(BACKUP_DIR)
    except InvalidGitRepositoryError:
        print("Initializing Git repository...")
        repo = Repo.init(BACKUP_DIR)
    return repo

def commit_to_git(repo, filename, hostname):
    """Commits the change to git."""
    try:
        repo.index.add([filename])
        if repo.is_dirty(untracked_files=True):
            repo.index.commit(f"Backup {hostname} - {get_timestamp()}")
            print(f"Committed changes for {hostname} to Git.")
        else:
            print(f"No changes detected for {hostname}.")
    except Exception as e:
        print(f"Git commit failed: {e}")

def backup_router(hostname, repo):
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
            
            # Save to a fixed filename for Git tracking
            filename = f"{hostname.strip()}.conf"
            filepath = os.path.join(BACKUP_DIR, filename)
            
            with open(filepath, "w") as f:
                f.write(config_output)
            
            print(f"Backup saved to {filepath}")
            
            # Commit to Git
            commit_to_git(repo, filename, hostname.strip())
            return True, None
            
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
        error_msg = f"Failed to connect to {hostname}: {e}"
        print(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"An error occurred with {hostname}: {e}"
        print(error_msg)
        return False, error_msg

def main():
    if not ROUTER_HOSTS or ROUTER_HOSTS == ['']:
        print("No routers configured in ROUTER_HOSTS.")
        return

    if not USERNAME or not PASSWORD:
        print("Credentials not found in environment variables.")
        return

    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # Initialize Git
    repo = init_git_repo()

    print(f"Starting backup job for {len(ROUTER_HOSTS)} routers.")
    
    success_hosts = []
    failed_hosts = []

    for host in ROUTER_HOSTS:
        if host:
            success, error = backup_router(host, repo)
            if success:
                success_hosts.append(host)
            else:
                failed_hosts.append(f"{host}: {error}")

    # Send Telegram Notification
    if failed_hosts:
        message = f"❌ *Backup Job Failed (Partial or Complete)*\n\n*Failed Routers:*\n" + "\n".join(failed_hosts)
        if success_hosts:
            message += f"\n\n*Successful Routers:* {', '.join(success_hosts)}"
        send_telegram_notification(message)
    elif success_hosts:
        message = f"✅ *Backup Job Completed Successfully*\n\nBacked up {len(success_hosts)} routers:\n" + ", ".join(success_hosts)
        send_telegram_notification(message)

    print("Backup job completed.")

if __name__ == "__main__":
    main()
