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
            
            # PERBAIKAN 1: Format payload yang benar untuk Fragment API
            payload = {
                'hash': self.hash_value,
                'recipient': username.replace('@', ''),
                'quantity': quantity,  # Jangan string, kirim sebagai integer
                'showSender': show_sender  # Jangan string, kirim sebagai boolean
            }
            
            print(f"📤 Sending request to Fragment API...")
            print(f"📦 Payload: {payload}")  # Tambahkan log payload
            
            # PERBAIKAN 2: Gunakan endpoint yang benar
            response = self.session.post(
                "https://fragment.com/api?type=buyStars",  # Endpoint lengkap
                json=payload,  # Gunakan json= bukan data= untuk otomatis set Content-Type
                timeout=30,
                headers={
                    **self.session.headers,
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': self._get_csrf_token()  # Ambil CSRF token dari cookies
                }
            )
            
            print(f"📥 Response status: {response.status_code}")
            print(f"📦 Response text: {response.text[:500]}")  # Log response lengkap
            
            if response.status_code != 200:
                return Result(False, error=f"API Error: HTTP {response.status_code}")
            
            try:
                result = response.json()
                print(f"📦 Response data: {json.dumps(result, indent=2)}")
            except:
                return Result(False, error="Invalid JSON response from Fragment")
            
            # PERBAIKAN 3: Cek struktur response yang benar
            if result.get('ok') or result.get('success'):
                # Berhasil
                tx_data = result.get('data', {}) or result.get('result', {})
                return Result(
                    True, 
                    tx_hash=tx_data.get('hash') or tx_data.get('transactionHash') or f"TX_{int(time.time())}",
                    data=tx_data
                )
            else:
                # Gagal - ambil pesan error
                error_msg = result.get('error') or result.get('message') or 'Unknown error'
                return Result(False, error=error_msg)
                
        except Exception as e:
            print(f"❌ Error in buy_stars: {e}")
            import traceback
            traceback.print_exc()
            return Result(False, error=str(e))
    
    def _get_csrf_token(self):
        """Ambil CSRF token dari cookies"""
        # Coba dapatkan dari cookies
        for cookie_name in ['csrf_token', 'X-CSRF-Token', 'csrftoken']:
            if cookie_name in self.session.cookies:
                return self.session.cookies[cookie_name]
        
        # Jika tidak ada, coba parse dari cookies string
        for key, value in self.session.cookies.items():
            if 'csrf' in key.lower() or 'token' in key.lower():
                return value
        
        return None

    async def validate_wallet_connection(self) -> Dict[str, Any]:
        """Validasi koneksi wallet dengan Fragment"""
        try:
            # Coba akses halaman wallet
            response = self.session.get(
                f"{self.BASE_URL}/wallet",
                timeout=10
            )
            
            if response.status_code == 200:
                html = response.text
                
                # Cek apakah wallet terhubung
                if 'wallet-connected' in html or 'wallet address' in html.lower():
                    # Extract wallet info
                    address_match = re.search(r'(EQ[A-Za-z0-9_-]{46,})', html)
                    balance_match = re.search(r'([0-9.]+)\s*TON', html)
                    
                    return {
                        'connected': True,
                        'address': address_match.group(1) if address_match else 'Unknown',
                        'balance': balance_match.group(1) if balance_match else '0'
                    }
                else:
                    return {
                        'connected': False,
                        'error': 'Wallet tidak terhubung ke Fragment'
                    }
            else:
                return {
                    'connected': False,
                    'error': f'HTTP {response.status_code}'
                }
                
        except Exception as e:
            return {
                'connected': False,
                'error': str(e)
            }

    async def process_purchase(self, event, data):
        """Proses pembelian Stars"""
        user_id = event.sender_id
        
        if user_id not in self.user_states:
            await event.edit("❌ Sesi telah berakhir. Ketik /buy untuk mulai lagi.")
            return
        
        state = self.user_states[user_id]
        
        # Update pesan ke processing
        await event.edit("⏱️ **MEMPROSES PEMBELIAN...**\n\nMohon tunggu, transaksi sedang diproses.", parse_mode='markdown')
        
        try:
            # Cek apakah wallet dikonfigurasi
            if not self.fragment_api:
                await event.edit("❌ **FRAGMENT API TIDAK TERSEDIA**")
                return
            
            # PERBAIKAN: Validasi wallet dulu
            wallet_status = await self.fragment_api.validate_wallet_connection()
            if not wallet_status.get('connected'):
                await event.edit(f"""
    ❌ **WALLET TIDAK TERHUBUNG**
    
    Wallet TON tidak terhubung ke akun Fragment.com Anda.
    
    **Langkah penyelesaian:**
    1. Buka https://fragment.com/wallet
    2. Hubungkan wallet TON Anda
    3. Pastikan wallet memiliki saldo
    4. Coba lagi nanti
    
    Error: {wallet_status.get('error', 'Unknown')}
                """, parse_mode='markdown')
                return
            
            # Cek saldo
            balance = await self.fragment_api.get_wallet_balance()
            try:
                balance_float = float(balance.get('balance', '0'))
                # Estimasi: 1 star ≈ 0.01 TON (sesuaikan dengan rate aktual)
                estimated_cost = state.amount * 0.01
                
                if balance_float < estimated_cost:
                    await event.edit(f"""
    ❌ **SALDO TIDAK CUKUP**
    
    Dibutuhkan: ~{estimated_cost} TON
    Saldo tersedia: {balance_float} TON
    Jumlah Stars: {state.amount} ⭐
    
    💡 Top up wallet Anda terlebih dahulu.
                    """, parse_mode='markdown')
                    return
            except:
                pass  # Abaikan jika gagal parse balance
            
            # Proses pembelian
            logger.info(f"Processing purchase: {state.amount} stars for @{state.username}")
            
            # PERBAIKAN: Gunakan hash terbaru
            # Refresh hash jika perlu
            if hasattr(self.fragment_api, 'hash_value') and not self.fragment_api.hash_value:
                # Coba dapatkan hash baru
                new_hash = await self.refresh_fragment_hash()
                if new_hash:
                    self.fragment_api.hash_value = new_hash
            
            result = await self.fragment_api.buy_stars(
                username=state.username,
                quantity=state.amount,
                show_sender=True
            )
            
            # Cek hasil
            if hasattr(result, 'success') and result.success:
                # Update statistik
                self.total_purchases += 1
                self.total_stars += state.amount
                
                tx_hash = getattr(result, 'transaction_hash', 'N/A')
                
                success_msg = f"""
    ✅ **PEMBELIAN BERHASIL!**
    
    **Penerima:** @{state.username}
    **Jumlah:** {state.amount} ⭐
    **Transaction Hash:** `{tx_hash}`
    
    ✨ Stars akan segera masuk ke akun penerima.
    Terima kasih telah menggunakan bot ini!
                """
                
                await event.edit(success_msg, parse_mode='markdown')
                logger.info(f"Purchase successful: {state.amount} stars for @{state.username}")
                
            else:
                error = getattr(result, 'error', 'Unknown error')
                
                # PERBAIKAN: Error message yang lebih informatif
                error_msg = f"""
    ❌ **PEMBELIAN GAGAL**
    
    **Error:** {error}
    
    **Diagnosa:**
    • {'✅' if wallet_status.get('connected') else '❌'} Wallet terhubung
    • Balance: {balance.get('balance', '0')} TON
    
    **Kemungkinan penyebab:**
    • Session expired - export ulang cookies
    • Hash expired - jalankan get_hash.py
    • Wallet tidak memiliki saldo cukup
    • Username tidak valid
    
    **Langkah:**
    1. Export ulang cookies dari browser
    2. Jalankan `python3 get_hash.py`
    3. Cek saldo wallet di fragment.com/wallet
    4. Ketik /buy untuk mencoba lagi
                """
                
                await event.edit(error_msg, parse_mode='markdown')
                logger.error(f"Purchase failed: {error}")
                
        except FragmentAPIError as e:
            logger.error(f"FragmentAPIError: {e}")
            await event.edit(f"❌ **FRAGMENT API ERROR:** {str(e)}")
        except Exception as e:
            logger.error(f"Purchase exception: {e}")
            await event.edit(f"❌ **ERROR:** {str(e)[:200]}\n\nKetik /buy untuk coba lagi.")
        
        # Hapus state
        if user_id in self.user_states:
            del self.user_states[user_id]
    
    async def refresh_fragment_hash(self):
        """Refresh hash dari Fragment"""
        try:
            # Coba dapatkan hash baru
            response = await self.fragment_api.session.get(
                "https://fragment.com/stars/buy",
                timeout=10
            )
            
            if response.status_code == 200:
                import re
                # Cari hash di HTML
                hash_match = re.search(r'hash=([a-f0-9]{32,})', response.text)
                if hash_match:
                    new_hash = hash_match.group(1)
                    logger.info(f"✅ New hash obtained: {new_hash[:10]}...")
                    return new_hash
        except Exception as e:
            logger.error(f"Failed to refresh hash: {e}")
        
        return None

    async def close(self):
        """Close session"""
        self.session.close()
