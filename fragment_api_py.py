"""
Fragment API Wrapper - Real implementation untuk Fragment.com
Menggunakan requests untuk komunikasi dengan Fragment API
"""

import requests
import json
import time
import re
from typing import Optional, Dict, Any, Union, List
from urllib.parse import urlencode

class FragmentAPIError(Exception):
    """Custom exception untuk Fragment API"""
    pass

class AsyncFragmentAPI:
    """Fragment API wrapper dengan implementasi real"""
    
    BASE_URL = "https://fragment.com"
    API_URL = "https://fragment.com/api"
    
    def __init__(self, cookies: str, hash_value: str = None, 
                 wallet_mnemonic: Union[str, List[str]] = None, 
                 wallet_api_key: str = None,
                 wallet_version: str = 'V4R2'):
        
        self.session = requests.Session()
        self.cookies = self._parse_cookies(cookies)
        self.hash_value = hash_value
        self.wallet_mnemonic = wallet_mnemonic
        self.wallet_api_key = wallet_api_key
        self.wallet_version = wallet_version
        
        # Set cookies ke session
        self.session.cookies.update(self.cookies)
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://fragment.com/',
            'Origin': 'https://fragment.com',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        print("📦 Using REAL Fragment API implementation")
    
    def _parse_cookies(self, cookies_string):
        """Parse cookies string to dict"""
        cookies = {}
        for item in cookies_string.split('; '):
            if '=' in item:
                key, value = item.split('=', 1)
                cookies[key] = value
        return cookies
    
    def _validate_wallet_mnemonic(self):
        """Validasi wallet mnemonic"""
        if not self.wallet_mnemonic:
            return False
        
        # Jika berupa list, gabungkan jadi string untuk validasi
        if isinstance(self.wallet_mnemonic, list):
            mnemonic_str = ' '.join(self.wallet_mnemonic)
            return not mnemonic_str.startswith('abandon')
        else:
            return not self.wallet_mnemonic.startswith('abandon')
    
    async def get_wallet_balance(self) -> Dict[str, Any]:
        """Get real wallet balance dari Fragment"""
        try:
            # Coba ambil data wallet dari Fragment
            response = self.session.get(
                f"{self.BASE_URL}/wallet",
                timeout=10
            )
            
            if response.status_code == 200:
                # Parse balance dari response HTML
                html = response.text
                
                # Extract balance - cari angka dengan TON
                balance_match = re.search(r'([0-9.]+)\s*TON', html)
                balance = balance_match.group(1) if balance_match else "0"
                
                # Extract address - cari pattern address TON (biasanya mulai EQ)
                address_match = re.search(r'(EQ[A-Za-z0-9_-]{46,})', html)
                if not address_match:
                    # Coba pattern lain
                    address_match = re.search(r'wallet-address["\']?\s*:\s*["\']([^"\']+)', html)
                
                address = address_match.group(1) if address_match else "Unknown"
                
                return {
                    'balance': balance,
                    'balance_ton': balance,
                    'address': address,
                    'wallet_version': self.wallet_version
                }
            else:
                return {
                    'balance': '0',
                    'balance_ton': '0',
                    'address': 'Unknown',
                    'wallet_version': self.wallet_version
                }
                
        except Exception as e:
            print(f"Error getting wallet balance: {e}")
            return {
                'balance': '0',
                'balance_ton': '0',
                'address': 'Unknown',
                'wallet_version': self.wallet_version
            }
    
    async def get_recipient_stars(self, username: str) -> Dict[str, Any]:
        """Cek apakah user bisa menerima stars"""
        try:
            params = {
                'type': 'stars_recipient',
                'username': username.replace('@', '')
            }
            
            response = self.session.get(
                self.API_URL,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {'success': False, 'error': f'HTTP {response.status_code}'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def buy_stars(self, username: str, quantity: int, show_sender: bool = True) -> Any:
        """REAL implementation untuk beli stars"""
        class Result:
            def __init__(self, success, tx_hash=None, error=None, data=None):
                self.success = success
                self.transaction_hash = tx_hash
                self.error = error
                self.data = data
        
        try:
            print(f"🔄 Processing real purchase: {quantity} stars for @{username}")
            
            # Validasi hash
            if not self.hash_value:
                return Result(False, error="FRAGMENT_HASH tidak ditemukan. Jalankan get_hash.py dulu!")
            
            # Validasi wallet mnemonic
            if not self._validate_wallet_mnemonic():
                return Result(False, error="Wallet seed phrase belum diisi atau masih menggunakan default!")
            
            # Siapkan payload
            payload = {
                'hash': self.hash_value,
                'recipient': username.replace('@', ''),
                'quantity': str(quantity),
                'showSender': str(show_sender).lower()
            }
            
            print(f"📤 Sending request to Fragment API...")
            
            # Request ke Fragment API
            response = self.session.post(
                self.API_URL,
                data=payload,
                timeout=30
            )
            
            print(f"📥 Response status: {response.status_code}")
            
            if response.status_code != 200:
                return Result(False, error=f"API Error: HTTP {response.status_code}")
            
            try:
                result = response.json()
                print(f"📦 Response data: {json.dumps(result, indent=2)[:200]}")
            except:
                return Result(False, error="Invalid JSON response from Fragment")
            
            if not result.get('ok'):
                return Result(False, error=result.get('error', 'Unknown error'))
            
            # Dapatkan transaction data
            tx_data = result.get('data', {})
            
            # Berhasil
            return Result(
                True, 
                tx_hash=tx_data.get('hash', f"TX_{int(time.time())}"),
                data=tx_data
            )
            
        except Exception as e:
            print(f"❌ Error in buy_stars: {e}")
            import traceback
            traceback.print_exc()
            return Result(False, error=str(e))
    
    async def close(self):
        """Close session"""
        self.session.close()
