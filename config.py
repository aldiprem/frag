import os
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Config:
    """Configuration class untuk bot"""
    
    # Telegram Config
    API_ID = int(os.getenv('API_ID', 0))
    API_HASH = os.getenv('API_HASH', '')
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    
    # Fragment Config
    FRAGMENT_COOKIES = os.getenv('FRAGMENT_COOKIES', '')
    FRAGMENT_HASH = os.getenv('FRAGMENT_HASH', '')
    
    # Wallet Config
    WALLET_MNEMONIC = os.getenv('WALLET_MNEMONIC', '')
    TON_API_KEY = os.getenv('TON_API_KEY', '')
    WALLET_VERSION = os.getenv('WALLET_VERSION', 'V4R2')
    
    # Bot Settings
    MIN_STARS = int(os.getenv('MIN_STARS', 1))
    MAX_STARS = int(os.getenv('MAX_STARS', 1000))
    DEFAULT_STARS = int(os.getenv('DEFAULT_STARS', 50))
    
    @classmethod
    def validate(cls):
        """Validasi semua konfigurasi"""
        errors = []
        warnings = []
        
        # Validasi Telegram
        if not cls.API_ID or cls.API_ID == 1234567:
            errors.append("❌ API_ID tidak valid. Dapatkan dari my.telegram.org")
        if not cls.API_HASH or cls.API_HASH == 'abcdef1234567890abcdef1234567890':
            errors.append("❌ API_HASH tidak valid. Dapatkan dari my.telegram.org")
        if not cls.BOT_TOKEN or cls.BOT_TOKEN.startswith('1234567890'):
            errors.append("❌ BOT_TOKEN tidak valid. Dapatkan dari @BotFather")
        
        # Validasi Fragment
        if not cls.FRAGMENT_COOKIES:
            errors.append("❌ FRAGMENT_COOKIES kosong. Export dari browser")
        elif 'stel_ssid' not in cls.FRAGMENT_COOKIES:
            errors.append("❌ FRAGMENT_COOKIES tidak valid. Harus mengandung stel_ssid")
        
        if not cls.FRAGMENT_HASH or cls.FRAGMENT_HASH == 'your_hash_here_32_characters_long':
            errors.append("❌ FRAGMENT_HASH belum diisi. Jalankan get_hash.py dulu")
        
        # Validasi Wallet
        if not cls.WALLET_MNEMONIC or cls.WALLET_MNEMONIC.startswith('abandon'):
            warnings.append("⚠️  WALLET_MNEMONIC menggunakan default. Ganti dengan seed phrase asli!")
        
        if not cls.TON_API_KEY or cls.TON_API_KEY == 'your_ton_api_key_here':
            warnings.append("⚠️  TON_API_KEY belum diisi. Dapatkan dari tonconsole.com")
        
        return errors, warnings
    
    @classmethod
    def display_config(cls):
        """Tampilkan konfigurasi (untuk debugging)"""
        print("\n" + "="*50)
        print("📋 KONFIGURASI BOT")
        print("="*50)
        
        # Telegram (sensor)
        print(f"🤖 API_ID: {cls.API_ID}")
        print(f"🤖 API_HASH: {cls.mask_string(cls.API_HASH)}")
        print(f"🤖 BOT_TOKEN: {cls.mask_string(cls.BOT_TOKEN)}")
        
        # Fragment
        cookies_preview = cls.FRAGMENT_COOKIES[:50] + "..." if cls.FRAGMENT_COOKIES else "Kosong"
        print(f"🍪 COOKIES: {cookies_preview}")
        print(f"🔑 HASH: {cls.mask_string(cls.FRAGMENT_HASH)}")
        
        # Wallet
        mnemonic_preview = " ".join(cls.WALLET_MNEMONIC.split()[:3]) + "..." if cls.WALLET_MNEMONIC else "Kosong"
        print(f"💰 WALLET: {mnemonic_preview}")
        print(f"🔐 VERSION: {cls.WALLET_VERSION}")
        
        # Settings
        print(f"⚙️  MIN STARS: {cls.MIN_STARS}")
        print(f"⚙️  MAX STARS: {cls.MAX_STARS}")
        print("="*50 + "\n")
    
    @staticmethod
    def mask_string(s, visible=4):
        """Mask string untuk keamanan"""
        if not s:
            return "Kosong"
        if len(s) <= visible * 2:
            return "*" * len(s)
        return s[:visible] + "*" * (len(s) - visible * 2) + s[-visible:]
