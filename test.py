#!/usr/bin/env python3
"""
Test Cookies Fragment.com
Cek apakah cookies valid dan bisa digunakan
"""

import os
import sys
import asyncio
import json
from datetime import datetime

# Load .env
from dotenv import load_dotenv
load_dotenv()

# Color codes for terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_banner():
    """Print banner"""
    banner = f"""
{Colors.CYAN}{Colors.BOLD}╔════════════════════════════════════════════════════════╗
║         FRAGMENT COOKIES TESTER v1.0                      ║
╚════════════════════════════════════════════════════════════╝{Colors.RESET}
    """
    print(banner)

def parse_cookies(cookies_string):
    """Parse cookies string to dict"""
    cookies = {}
    try:
        for item in cookies_string.split('; '):
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key.strip()] = value.strip()
    except Exception as e:
        print(f"{Colors.RED}Error parsing cookies: {e}{Colors.RESET}")
    return cookies

async def test_cookies():
    """Test cookies dengan Fragment API"""
    
    print_banner()
    
    # Load cookies dari environment
    cookies_string = os.getenv('FRAGMENT_COOKIES', '')
    fragment_hash = os.getenv('FRAGMENT_HASH', '')
    
    if not cookies_string:
        print(f"{Colors.RED}❌ FRAGMENT_COOKIES tidak ditemukan di .env{Colors.RESET}")
        print("Pastikan sudah mengisi file .env dengan benar")
        return False
    
    print(f"{Colors.BLUE}{Colors.BOLD}📋 INFORMASI COOKIES{Colors.RESET}")
    print("-" * 50)
    
    # Parse dan tampilkan cookies
    cookies = parse_cookies(cookies_string)
    
    required_cookies = ['stel_ssid', 'stel_token', 'stel_ton_token']
    missing = []
    
    for rc in required_cookies:
        if rc in cookies:
            value = cookies[rc]
            preview = value[:20] + "..." if len(value) > 20 else value
            print(f"{Colors.GREEN}✅ {rc}: {preview}{Colors.RESET}")
        else:
            print(f"{Colors.RED}❌ {rc}: MISSING{Colors.RESET}")
            missing.append(rc)
    
    if missing:
        print(f"\n{Colors.RED}❌ Cookies tidak lengkap. Missing: {', '.join(missing)}{Colors.RESET}")
        return False
    
    print(f"\n{Colors.BLUE}{Colors.BOLD}🔍 TESTING KONEKSI{Colors.RESET}")
    print("-" * 50)
    
    # Cek Fragment API
    try:
        # Import FragmentAPI
        from fragment_api_py import AsyncFragmentAPI
        
        print(f"{Colors.YELLOW}⏳ Mencoba koneksi ke Fragment.com...{Colors.RESET}")
        
        # Inisialisasi API
        api = AsyncFragmentAPI(
            cookies=cookies_string,
            hash_value=fragment_hash if fragment_hash else None
        )
        
        # Test dengan get_recipient_stars
        try:
            result = await api.get_recipient_stars('telegram')
            print(f"{Colors.GREEN}✅ Koneksi berhasil! Cookies valid.{Colors.RESET}")
        except Exception as e:
            if "401" in str(e):
                print(f"{Colors.RED}❌ Unauthorized: Cookies expired atau tidak valid{Colors.RESET}")
                print("   Export ulang cookies dari browser")
            else:
                print(f"{Colors.YELLOW}⚠️  Response: {str(e)[:100]}{Colors.RESET}")
                print("   Cookies mungkin valid tapi perlu hash")
        
        # Cek wallet
        print(f"\n{Colors.YELLOW}⏳ Mengecek wallet...{Colors.RESET}")
        
        if os.getenv('WALLET_MNEMONIC') and not os.getenv('WALLET_MNEMONIC').startswith('abandon'):
            try:
                # Reinit dengan wallet
                api = AsyncFragmentAPI(
                    cookies=cookies_string,
                    hash_value=fragment_hash,
                    wallet_mnemonic=os.getenv('WALLET_MNEMONIC'),
                    wallet_api_key=os.getenv('TON_API_KEY'),
                    wallet_version=os.getenv('WALLET_VERSION', 'V4R2')
                )
                
                balance = await api.get_wallet_balance()
                print(f"{Colors.GREEN}✅ Wallet terhubung!{Colors.RESET}")
                print(f"   Balance: {balance.get('balance_ton', 'Unknown')} TON")
                print(f"   Address: {balance.get('address', 'Unknown')[:15]}...")
            except Exception as e:
                print(f"{Colors.YELLOW}⚠️  Wallet belum dikonfigurasi: {str(e)[:100]}{Colors.RESET}")
        else:
            print(f"{Colors.YELLOW}⚠️  Wallet seed phrase belum diisi (gunakan yang asli untuk transaksi){Colors.RESET}")
        
        print(f"\n{Colors.GREEN}{Colors.BOLD}✅ TESTING SELESAI!{Colors.RESET}")
        print("-" * 50)
        
        # Rekomendasi
        if fragment_hash:
            print(f"Hash: {fragment_hash[:15]}... (OK)")
        else:
            print(f"{Colors.YELLOW}⚠️  FRAGMENT_HASH kosong - perlu diisi untuk transaksi{Colors.RESET}")
        
        return True
        
    except ImportError:
        print(f"{Colors.RED}❌ FragmentAPI tidak terinstall. Jalankan: pip install fragment-api-py{Colors.RESET}")
        return False
    except Exception as e:
        print(f"{Colors.RED}❌ Error: {e}{Colors.RESET}")
        return False

async def main():
    """Main function"""
    success = await test_cookies()
    
    if success:
        print(f"\n{Colors.GREEN}Cookies siap digunakan!{Colors.RESET}")
    else:
        print(f"\n{Colors.RED}Cookies bermasalah. Silakan perbaiki.{Colors.RESET}")
    
    print("\nTekan Enter untuk keluar...")
    input()

if __name__ == "__main__":
    asyncio.run(main())
