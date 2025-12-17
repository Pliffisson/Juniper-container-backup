import os
import datetime
import glob
import requests
import threading
import concurrent.futures
import yaml
import logging
import schedule
import time
from logging.handlers import RotatingFileHandler
from git import Repo, InvalidGitRepositoryError
from netmiko import ConnectHandler, NetmikoTimeoutException, NetmikoAuthenticationException
from dotenv import load_dotenv
from jsonschema import validate, ValidationError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Load environment variables
load_dotenv()

# Configuration
PORT = os.getenv("PORT", "22")
BACKUP_DIR = os.getenv("BACKUP_DIR", "/backups")
# Log to stdout by default for Docker. If LOG_FILE is set, it will ALSO log to file.
LOG_FILE = os.getenv("LOG_FILE", "/var/log/backup.log") 
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BACKUP_INTERVAL_MINUTES = int(os.getenv("BACKUP_INTERVAL_MINUTES", "60"))

# Determine absolute path to inventory.yaml (one directory up from src/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INVENTORY_FILE = os.path.join(BASE_DIR, "inventory.yaml")

# Platform/Command Map - REMOVED (Juniper Only)
# Juniper Command
JUNIPER_COMMAND = "show configuration | display set"

# Lock for Git operations to prevent race conditions
GIT_LOCK = threading.Lock()

# Inventory validation schema
INVENTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "routers": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["host"],
                "properties": {
                    "host": {
                        "type": "string",
                        "minLength": 1,
                        "description": "IP address or hostname of the device"
                    },
                    "port": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 65535,
                        "description": "SSH port number"
                    },
                    "username": {
                        "type": "string",
                        "minLength": 1,
                        "description": "SSH username"
                    },
                    "password": {
                        "type": "string",
                        "minLength": 1,
                        "description": "SSH password"
                    }
                },
                "additionalProperties": True  # Allow extra fields for flexibility
            }
        }
    },
    "required": ["routers"],
    "additionalProperties": True
}

# Logging Configuration
logger = logging.getLogger("BackupJob")
logger.setLevel(logging.INFO)

# Formatter with enhanced date/time format
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
)

# Stream Handler (stdout) - Always Active for Docker
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# File Handler (Optional/Rotating)
# Only try to file log if explicit path given and writable
try:
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except Exception as e:
    # Non-critical failure, we still have stdout
    logger.warning(f"Could not setup file logging (likely permission issue, strictly using stdout): {e}")


def get_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def send_telegram_notification(message):
    """Sends a notification to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured. Skipping notification.")
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
        logger.info("Telegram notification sent.")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def init_git_repo():
    """Initializes a git repository in the backup directory if it doesn't exist."""
    try:
        repo = Repo(BACKUP_DIR)
    except InvalidGitRepositoryError:
        logger.info("Initializing Git repository...")
        repo = Repo.init(BACKUP_DIR)
    return repo

MAX_BACKUPS = int(os.getenv("MAX_BACKUPS", "10"))

def commit_to_git(repo, filename, hostname):
    """Commits the change to git."""
    try:
        repo.index.add([filename])
        # Always commit since filename is unique
        repo.index.commit(f"Backup {hostname} - {filename}")
        logger.info(f"Committed {filename} to Git.")
    except Exception as e:
        logger.error(f"Git commit failed: {e}", exc_info=True)

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
                logger.info(f"Deleted old backup: {f}")
    except Exception as e:
        logger.error(f"Cleanup failed for {hostname}: {e}", exc_info=True)

def validate_environment():
    """Validates critical environment variables."""
    warnings = []
    
    # Check for credentials (either in env or will be in inventory)
    if not os.getenv("JUNIPER_USERNAME"):
        warnings.append("JUNIPER_USERNAME not set - ensure all devices have credentials in inventory.yaml")
    
    if not os.getenv("JUNIPER_PASSWORD"):
        warnings.append("JUNIPER_PASSWORD not set - ensure all devices have credentials in inventory.yaml")
    
    # Check Telegram config (optional but warn if incomplete)
    has_token = bool(TELEGRAM_BOT_TOKEN)
    has_chat_id = bool(TELEGRAM_CHAT_ID)
    
    if has_token != has_chat_id:
        warnings.append("Telegram configuration incomplete - both BOT_TOKEN and CHAT_ID required for notifications")
    
    # Log warnings
    for warning in warnings:
        logger.warning(warning)
    
    return len(warnings) == 0


def load_inventory():
    """Loads and validates device inventory from YAML file."""
    if not os.path.exists(INVENTORY_FILE):
        logger.error(f"Inventory file {INVENTORY_FILE} not found.")
        return []
    
    try:
        with open(INVENTORY_FILE, 'r') as f:
            data = yaml.safe_load(f)
        
        # Validate against schema
        try:
            validate(instance=data, schema=INVENTORY_SCHEMA)
            logger.info(f"Inventory validation passed: {len(data.get('routers', []))} devices found")
        except ValidationError as ve:
            logger.error(f"Inventory validation failed: {ve.message}")
            logger.error(f"Failed at path: {' -> '.join(str(p) for p in ve.path)}")
            logger.error("Please check your inventory.yaml file format")
            return []
        
        return data.get('routers', [])
        
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error in inventory file: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Error loading inventory: {e}", exc_info=True)
        return []

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=16),
    retry=retry_if_exception_type((NetmikoTimeoutException, ConnectionError, TimeoutError)),
    reraise=True,
    before_sleep=lambda retry_state: logger.warning(
        f"Retry attempt {retry_state.attempt_number} for {retry_state.args[0].get('host', 'unknown')} "
        f"after {retry_state.outcome.exception()}"
    )
)
def backup_router(device_info, repo):
    host = device_info.get('host')
    # Use 'platform' if provided for compatibility, but default/enforce juniper_junos logic
    # We ignore the inventory platform and force juniper_junos as requested
    platform = "juniper_junos"
    
    # Default to environment variables if not in inventory
    username = device_info.get('username', os.getenv("JUNIPER_USERNAME"))
    password = device_info.get('password', os.getenv("JUNIPER_PASSWORD"))
    port = device_info.get('port', PORT)

    logger.info(f"Starting backup for {host} (Juniper)...")
    start_time = datetime.datetime.now()
    
    # Validation
    if not host or not username or not password:
         error_msg = f"Missing configuration for host {host}"
         logger.error(error_msg)
         return False, error_msg

    device = {
        "device_type": "juniper_junos",
        "host": host,
        "username": username,
        "password": password,
        "port": port,
        # Increase timeout for large configs
        "global_delay_factor": 2, 
    }

    try:
        with ConnectHandler(**device) as net_connect:
            logger.info(f"Connected to {host}")
            
            # Get device hostname
            try:
                 device_hostname_output = net_connect.send_command("show configuration system host-name")
                 device_hostname = device_hostname_output.split()[-1] if device_hostname_output else host
            except:
                device_hostname = host

            # Sanitize hostname
            device_hostname = device_hostname.replace(";", "").replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
            
            # Get configuration
            config_output = net_connect.send_command(JUNIPER_COMMAND)
            
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
            
            logger.info(f"Backup saved to {filepath}")
            
            # Critical section: Git operations and cleanup must be sequential
            with GIT_LOCK:
                # Commit to Git
                commit_to_git(repo, filename, device_hostname)
                
                # Cleanup old backups using device hostname
                cleanup_old_backups(device_hostname)
            
            # Return success with details
            return True, {
                "hostname": device_hostname,
                "ip": host,
                "filename": filename,
                "size_kb": file_size_kb,
                "duration": duration,
                "timestamp": timestamp
            }
            
    except (NetmikoTimeoutException, NetmikoAuthenticationException) as e:
        error_msg = f"Failed to connect to {host}: {e}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"An error occurred with {host}: {e}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

def update_healthcheck_timestamp():
    """Updates timestamp file for healthcheck monitoring."""
    try:
        with open('/tmp/last_run', 'w') as f:
            f.write(str(time.time()))
    except Exception as e:
        logger.warning(f"Could not update healthcheck timestamp: {e}")


def run_backup_job():
    logger.info("="*80)
    logger.info("🔧 INICIANDO BACKUP JOB")
    logger.info("="*80)
    
    # Update healthcheck timestamp at start
    update_healthcheck_timestamp()
    
    # Ensure backup directory exists
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
    except Exception as e:
        logger.error(f"Failed to create backup dir {BACKUP_DIR}: {e}")
        # Continue might fail if dir doesn't exist, but maybe it does
    
    # Initialize Git (if fails, we might still proceed with file backup)
    try:
        repo = init_git_repo()
    except Exception as e:
        logger.error(f"Failed to init git repo: {e}")
        repo = None

    routers = load_inventory()
    
    if not routers:
        logger.warning("No routers found in inventory.yaml.")
        return

    logger.info(f"Starting backup for {len(routers)} devices.")
    job_start_time = datetime.datetime.now()
    
    success_details = []
    failed_hosts = []

    # Use ThreadPoolExecutor for parallel backups
    max_workers = min(len(routers), 10)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit tasks
        future_to_host = {executor.submit(backup_router, router, repo): router.get('host') for router in routers}
        
        for future in concurrent.futures.as_completed(future_to_host):
            host = future_to_host[future]
            try:
                success, result = future.result()
                if success:
                    success_details.append(result)
                else:
                    failed_hosts.append({"ip": host, "error": result})
            except Exception as exc:
                failed_hosts.append({"ip": host, "error": f"Thread exception: {exc}"})

    job_end_time = datetime.datetime.now()
    total_duration = (job_end_time - job_start_time).total_seconds()

    # Send Telegram Notification
    if failed_hosts or success_details:
        total_routers = len(routers)
        success_count = len(success_details)
        total_size_mb = sum(d['size_kb'] for d in success_details) / 1024
        
        # Header
        message_lines = []
        message_lines.append("🔧 *JUNIPER BACKUP SYSTEM*")
        message_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        message_lines.append("")
        
        # Metrics
        message_lines.append(f"📅 *Data/Hora:* `{job_end_time.strftime('%d/%m/%Y %H:%M:%S')}`")
        message_lines.append(f"⏱️ *Duração:* `{int(total_duration)}s`")
        message_lines.append("")
        
        # Success Icon/Count
        if failed_hosts:
            message_lines.append(f"⚠️ *Status:* `{success_count}/{total_routers} Sucessos`")
        else:
            message_lines.append(f"✅ *Status:* `{success_count}/{total_routers} Sucessos`")
        message_lines.append("")

        # Device List (Success)
        if success_details:
            message_lines.append("*✅ Dispositivos com Sucesso:*")
            for detail in success_details:
                size_str = f"{detail['size_kb']/1024:.2f}MB"
                message_lines.append(f"  • `{detail['hostname']}` ({size_str})")
            message_lines.append("")
        
        # Device List (Failure)
        if failed_hosts:
            message_lines.append("*❌ Falhas:*")
            for failed in failed_hosts:
                error_msg = str(failed['error'])[:50]
                message_lines.append(f"  • `{failed['ip']}`")
                message_lines.append(f"     ↳ _{error_msg}_")
            message_lines.append("")
            
        # Footer
        message_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
        if not failed_hosts:
            message_lines.append(f"🎉 *Backup Concluído!*")
            message_lines.append(f"📊 Total: `{len(success_details)} arquivos` • `{total_size_mb:.2f}MB`")
        else:
            message_lines.append(f"⚠️ *Backup finalizado com erros*")

        message = "\n".join(message_lines)
        send_telegram_notification(message)

    # Update healthcheck timestamp at end
    update_healthcheck_timestamp()
    
    logger.info("✅ BACKUP JOB CONCLUÍDO")
    logger.info("="*80)
    logger.info("")  # Linha em branco para separar jobs

def main():
    logger.info("Starting Backup Application (Non-Root)...")
    logger.info(f"Python version: {os.sys.version}")
    
    # Validate environment
    validate_environment()
    
    # Disabled: Run backup immediately on startup
    # This prevents duplicate notifications when container restarts
    # To run manually: docker exec juniper-backup python src/backup.py
    # run_backup_job()
    
    # Scheduling Logic
    backup_time = os.getenv("BACKUP_TIME")
    
    if backup_time:
        logger.info(f"Schedule: Daily at {backup_time}.")
        schedule.every().day.at(backup_time).do(run_backup_job)
    else:
        logger.info(f"Schedule: Every {BACKUP_INTERVAL_MINUTES} minutes.")
        schedule.every(BACKUP_INTERVAL_MINUTES).minutes.do(run_backup_job)
    
    # Loop
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
