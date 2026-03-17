# backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from bot_client import FragmentBotClient
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)  # Izinkan request dari website

# Inisialisasi bot client
bot_client = FragmentBotClient(
    api_id=int(os.getenv('API_ID')),
    api_hash=os.getenv('API_HASH'),
    bot_token=os.getenv('BOT_TOKEN'),
    cookies=os.getenv('COOKIES'),
    hash=os.getenv('HASH'),
    wallet_api_key=os.getenv('WALLET_API_KEY'),
    wallet_mnemonic=eval(os.getenv('WALLET_MNEMONIC'))
)

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/check-user', methods=['POST'])
async def check_user():
    """Cek apakah username valid di Fragment"""
    data = request.json
    username = data.get('username', '').replace('@', '')
    
    if not username:
        return jsonify({'error': 'Username required'}), 400
    
    user_info = await bot_client.get_user_info(username)
    
    if user_info:
        return jsonify({
            'found': True,
            'nickname': user_info['nickname'],
            'address': user_info['address']
        })
    else:
        return jsonify({'found': False})

@app.route('/api/calculate-price', methods=['POST'])
def calculate_price():
    """Hitung harga stars"""
    data = request.json
    stars = int(data.get('stars', 0))
    price_per_star = float(os.getenv('PRICE_PER_STAR', 0.02))
    
    return jsonify({
        'stars': stars,
        'price_per_star': price_per_star,
        'total': stars * price_per_star
    })

@app.route('/api/purchase', methods=['POST'])
async def purchase():
    """Proses pembelian stars"""
    data = request.json
    username = data.get('username', '').replace('@', '')
    stars = int(data.get('stars', 0))
    show_sender = data.get('show_sender', True)
    
    if not username or stars < 10:
        return jsonify({'error': 'Invalid parameters'}), 400
    
    try:
        # Panggil fungsi dari bot_client
        tx_hash = await bot_client.purchase_stars(
            username=username,
            quantity=stars,
            show_sender=show_sender
        )
        
        if tx_hash:
            return jsonify({
                'success': True,
                'tx_hash': tx_hash,
                'recipient': username,
                'stars': stars
            })
        else:
            return jsonify({'success': False, 'error': 'Purchase failed'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5500, debug=True)
