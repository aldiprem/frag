# backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import aiohttp
import base64
import json
import os
from dotenv import load_dotenv
from tonutils.client import TonapiClient
from tonutils.wallet import WalletV5R1

load_dotenv()

app = Flask(__name__)
# Izinkan request dari GitHub Pages Anda
CORS(app, origins=['https://aldiprem.github.io'])

# Konfigurasi dari environment
COOKIES = os.getenv('COOKIES')
HASH = os.getenv('HASH')
WALLET_API_KEY = os.getenv('WALLET_API_KEY')
WALLET_MNEMONIC = json.loads(os.getenv('WALLET_MNEMONIC', '[]'))

async def post_fragment(data):
    """Fungsi POST ke Fragment API (salin dari b.py Anda)"""
    params = {"hash": HASH}
    headers = {
        "accept": "application/json",
        "cookie": COOKIES,
        "user-agent": "Mozilla/5.0",
        "x-requested-with": "XMLHttpRequest",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://fragment.com/api", params=params, headers=headers, data=data) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

@app.route('/api/purchase', methods=['POST'])
async def purchase():
    try:
        data = request.json
        username = data.get('username', '').replace('@', '')
        quantity = int(data.get('stars', 0))
        show_sender = data.get('show_sender', True)

        # --- Logika dari b.py Anda ---
        # 1. Cari user
        user = await post_fragment({"query": username, "method": "searchStarsRecipient"})
        if not user or not user.get('found'):
            return jsonify({'success': False, 'error': 'User not found'})
        
        address = user['found']['recipient']

        # 2. Init buy
        init = await post_fragment({"recipient": address, "quantity": quantity, "method": "initBuyStarsRequest"})
        if not init or 'req_id' not in init:
            return jsonify({'success': False, 'error': 'Failed to init purchase'})

        # 3. Get payment details
        buy = await post_fragment({
            "transaction": "1",
            "id": init['req_id'],
            "show_sender": "1" if show_sender else "0",
            "method": "getBuyStarsLink"
        })
        if not buy:
            return jsonify({'success': False, 'error': 'Failed to get payment details'})

        msg = buy['transaction']['messages'][0]
        payload = base64.b64decode(msg['payload']).decode('utf-8', errors='ignore')

        # 4. Send TON
        client = TonapiClient(api_key=WALLET_API_KEY)
        wallet, _, _, _ = WalletV5R1.from_mnemonic(client, WALLET_MNEMONIC)
        tx_hash = await wallet.transfer(
            destination=msg['address'],
            amount=int(msg['amount']) / 1_000_000_000,
            body=payload
        )

        return jsonify({'success': True, 'tx_hash': tx_hash})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5500, debug=True) 
