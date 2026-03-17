#!/usr/bin/env python3
"""
Get Fragment Hash from Browser
Script untuk mendapatkan hash dari Fragment.com
"""

import re
import json
import requests
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import os

# Color codes
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

load_dotenv()

def print_banner():
    """Print banner"""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}╔════════════════════════════════════════════════════════╗
║         FRAGMENT HASH EXTRACTOR v1.0                      ║
╚════════════════════════════════════════════════════════════╝{Colors.RESET}
    """
    print(banner)

def parse_cookies_from_env():
    """Parse cookies dari .env"""
    cookies_string = os.getenv('FRAGMENT_COOKIES', '')
    cookies = {}
    
    for item in cookies_string.split('; '):
        if '=' in item:
            key, value = item.split('=', 1)
            cookies[key] = value
    
    return cookies

def extract_hash_from_url(url):
    """Extract hash dari URL"""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    return params.get('hash', [None])[0]

def get_hash_from_webpage():
    """Coba dapatkan hash dari webpage"""
    
    print(f"{Colors.BLUE}{Colors.BOLD}📋 METODE 1: Extract dari Webpage{Colors.RESET}")
    print("-" * 50)
    
    cookies = parse_cookies_from_env()
    
    if not cookies:
        print(f"{Colors.RED}❌ Tidak ada cookies di .env{Colors.RESET}")
        return None
    
    print(f"{Colors.GREEN}✅ Cookies loaded: {', '.join(cookies.keys())}{Colors.RESET}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        # Coba akses halaman utama
        print(f"{Colors.YELLOW}⏳ Mengakses fragment.com...{Colors.RESET}")
        response = requests.get('https://fragment.com', cookies=cookies, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print(f"{Colors.GREEN}✅ Halaman utama loaded{Colors.RESET}")
            
            # Cari hash di HTML
            hash_patterns = [
                r'hash["\']?\s*[:=]\s*["\']([a-f0-9]{32,})["\']',
                r'hash=([a-f0-9]{32,})',
                r'api\?hash=([a-f0-9]{32,})',
                r'data-hash=["\']([a-f0-9]{32,})["\']'
            ]
            
            for pattern in hash_patterns:
                matches = re.findall(pattern, response.text, re.IGNORECASE)
                if matches:
                    hash_value = matches[0]
                    print(f"{Colors.GREEN}✅ Hash ditemukan di HTML: {hash_value}{Colors.RESET}")
                    return hash_value
            
            print(f"{Colors.YELLOW}⚠️  Hash tidak ditemukan di HTML{Colors.RESET}")
        else:
            print(f"{Colors.RED}❌ Gagal akses: HTTP {response.status_code}{Colors.RESET}")
            
    except Exception as e:
        print(f"{Colors.RED}❌ Error: {e}{Colors.RESET}")
    
    return None

def manual_hash_input():
    """Manual input hash"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}📋 METODE 2: Manual Input{Colors.RESET}")
    print("-" * 50)
    print("Cara mendapatkan hash manual:")
    print("1. Buka https://fragment.com/stars/buy")
    print("2. Pilih user dan jumlah stars (jangan bayar!)")
    print("3. Buka Developer Tools (F12)")
    print("4. Klik tab 'Network'")
    print("5. Cari request ke 'api?hash=...'")
    print("6. Copy nilai hash dari URL")
    print("-" * 50)
    
    hash_input = input(f"{Colors.CYAN}Masukkan hash (atau Enter untuk skip): {Colors.RESET}").strip()
    
    if hash_input and re.match(r'^[a-f0-9]{32,}$', hash_input, re.IGNORECASE):
        return hash_input
    
    return None

def update_env_file(hash_value):
    """Update .env file dengan hash baru"""
    env_file = '.env'
    
    try:
        with open(env_file, 'r') as f:
            lines = f.readlines()
        
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('FRAGMENT_HASH='):
                lines[i] = f'FRAGMENT_HASH={hash_value}\n'
                updated = True
                break
        
        if not updated:
            lines.append(f'\nFRAGMENT_HASH={hash_value}\n')
        
        with open(env_file, 'w') as f:
            f.writelines(lines)
        
        return True
    except Exception as e:
        print(f"{Colors.RED}Error update .env: {e}{Colors.RESET}")
        return False

def main():
    """Main function"""
    print_banner()
    
    # Cek cookies dulu
    cookies = parse_cookies_from_env()
    if not cookies:
        print(f"{Colors.RED}❌ Cookies tidak ditemukan di .env{Colors.RESET}")
        print("Pastikan FRAGMENT_COOKIES sudah diisi di file .env")
        return
    
    print(f"{Colors.GREEN}✅ Cookies ditemukan untuk domain: fragment.com{Colors.RESET}")
    print()
    
    # Coba metode 1
    hash1 = get_hash_from_webpage()
    
    # Jika gagal, minta manual
    hash2 = None
    if not hash1:
        hash2 = manual_hash_input()
    
    final_hash = hash1 or hash2
    
    if final_hash:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ HASH DITEMUKAN: {final_hash}{Colors.RESET}")
        
        # Update .env
        if update_env_file(final_hash):
            print(f"{Colors.GREEN}✅ Hash berhasil disimpan ke .env{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}⚠️  Gagal update .env, copy manual:{Colors.RESET}")
            print(f"FRAGMENT_HASH={final_hash}")
    else:
        print(f"\n{Colors.RED}❌ Tidak bisa mendapatkan hash{Colors.RESET}")
        print("Silakan dapatkan manual dari Developer Tools")

if __name__ == "__main__":
    main()
