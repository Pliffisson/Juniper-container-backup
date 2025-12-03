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
PORT = os.getenv("PORT", "22")
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

MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "10"))

def commit_to_git(repo, filename, hostname):
    """Commits the change to git."""
    try:
        repo.index.add([filename])
        # Always commit since filename is unique
        repo.index.commit(f"Backup {hostname} - {filename}")
        print(f"Committed {filename} to Git.")
    except Exception as e:
        print(f"Git commit failed: {e}")

def cleanup_old_backups(hostname):
    """Keeps only the last N backups for a given hostname."""
    try:
        # Find all backups for this hostname
        pattern = os.path.join(BACKUP_DIR, f"{hostname}_*.conf")
        files = glob.glob(pattern)
        
        # Sort by modification time (newest last)
        files.sort(key=os.path.getmtime)
        
        if len(files) > MAX_BACKUPS:
            files_to_delete = files[:-MAX_BACKUPS]
            for f in files_to_delete:
                os.remove(f)
                print(f"Deleted old backup: {f}")
                
                # Optional: Remove from git index if you want to keep git clean, 
                # but usually we keep history in git and only clean disk.
                # If we want to remove from git as well:
                # repo.index.remove([f]) 
    except Exception as e:
        print(f"Cleanup failed for {hostname}: {e}")

def backup_router(hostname, repo):
    print(f"Starting backup for {hostname}...")
    start_time = datetime.datetime.now()
    
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
            
            # Get device hostname
            device_hostname_output = net_connect.send_command("show configuration system host-name")
            # Extract hostname from output (format: "set system host-name HOSTNAME")
            device_hostname = device_hostname_output.split()[-1] if device_hostname_output else hostname.strip()
            
            # Sanitize hostname: remove special characters that could cause issues in filenames
            device_hostname = device_hostname.replace(";", "").replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
            
            # Get configuration
            config_output = net_connect.send_command("show configuration | display set")
            
            # Save to a timestamped filename using device hostname
            timestamp = get_timestamp()
            filename = f"{device_hostname}_{timestamp}.conf"
            filepath = os.path.join(BACKUP_DIR, filename)
            
            with open(filepath, "w") as f:
                f.write(config_output)
            
            # Get file size
            file_size = os.path.getsize(filepath)
            file_size_kb = file_size / 1024
            
            # Calculate duration
            end_time = datetime.datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            print(f"Backup saved to {filepath}")
            
            # Commit to Git
            commit_to_git(repo, filename, device_hostname)
            
            # Cleanup old backups using device hostname
            cleanup_old_backups(device_hostname)
            
            # Return success with details
            return True, {
                "hostname": device_hostname,
                "ip": hostname.strip(),
                "filename": filename,
                "size_kb": file_size_kb,
                "duration": duration,
                "timestamp": timestamp
            }
            
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
    job_start_time = datetime.datetime.now()
    
    success_details = []
    failed_hosts = []

    for host in ROUTER_HOSTS:
        if host:
            success, result = backup_router(host, repo)
            if success:
                success_details.append(result)
            else:
                failed_hosts.append({"ip": host.strip(), "error": result})

    job_end_time = datetime.datetime.now()
    total_duration = (job_end_time - job_start_time).total_seconds()

    # Send Telegram Notification
    if failed_hosts or success_details:
        # Build enhanced message
        message_lines = []
        
        if failed_hosts:
            message_lines.append("🔴 *BACKUP JOB - FALHA PARCIAL*")
        else:
            message_lines.append("✅ *BACKUP JOB - SUCESSO*")
        
        message_lines.append("━━━━━━━━━━━━━━━━━━━━")
        
        # Job summary
        message_lines.append(f"📊 *Resumo da Execução*")
        message_lines.append(f"• Total de dispositivos: `{len(ROUTER_HOSTS)}`")
        message_lines.append(f"• Sucesso: `{len(success_details)}`")
        message_lines.append(f"• Falhas: `{len(failed_hosts)}`")
        message_lines.append(f"• Duração total: `{total_duration:.2f}s`")
        message_lines.append(f"• Horário: `{job_end_time.strftime('%d/%m/%Y %H:%M:%S')}`")
        message_lines.append("")
        
        # Success details
        if success_details:
            message_lines.append("✅ *Backups Realizados*")
            message_lines.append("━━━━━━━━━━━━━━━━━━━━")
            for detail in success_details:
                message_lines.append(f"🖥 *{detail['hostname']}*")
                message_lines.append(f"  • Arquivo: `{detail['filename']}`")
                message_lines.append(f"  • Tamanho: `{detail['size_kb']:.2f} KB`")
                message_lines.append(f"  • Tempo: `{detail['duration']:.2f}s`")
                message_lines.append("")
        
        # Failed details
        if failed_hosts:
            message_lines.append("❌ *Falhas*")
            message_lines.append("━━━━━━━━━━━━━━━━━━━━")
            for failed in failed_hosts:
                message_lines.append(f"🖥 IP: `{failed['ip']}`")
                message_lines.append(f"  • Erro: `{failed['error']}`")
                message_lines.append("")
        
        message = "\n".join(message_lines)
        send_telegram_notification(message)

    print("Backup job completed.")

if __name__ == "__main__":
    main()
