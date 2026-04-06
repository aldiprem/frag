# app.py
from flask import Flask, render_template, jsonify, request, session
from functools import wraps
import os
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_TYPE'] = 'filesystem'

# Dummy data untuk demo (nanti akan connect ke database)
DUMMY_BOTS = [
    {
        'id': 1,
        'name': 'StarShop Bot',
        'username': '@starshop_bot',
        'status': 'active',
        'users': 1250,
        'stars_sold': 45200,
        'created_at': '2026-01-15'
    },
    {
        'id': 2,
        'name': 'Fragment Store',
        'username': '@fragmentstore_bot',
        'status': 'inactive',
        'users': 890,
        'stars_sold': 28300,
        'created_at': '2026-02-20'
    },
    {
        'id': 3,
        'name': 'Stars Vending',
        'username': '@starsvending_bot',
        'status': 'active',
        'users': 2340,
        'stars_sold': 124500,
        'created_at': '2026-03-01'
    }
]

DUMMY_PRICING = [
    {'stars': 50, 'price': 13500, 'discount': 0},
    {'stars': 100, 'price': 27000, 'discount': 0},
    {'stars': 500, 'price': 135000, 'discount': 5},
    {'stars': 1000, 'price': 270000, 'discount': 10},
    {'stars': 5000, 'price': 1350000, 'discount': 15},
    {'stars': 10000, 'price': 2700000, 'discount': 20},
]

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Main landing page / lobby"""
    return render_template('index.html')

@app.route('/api/pricing')
def get_pricing():
    """Get pricing list for stars"""
    return jsonify({
        'success': True,
        'pricing': DUMMY_PRICING,
        'min_stars': 10,
        'max_stars': 100000
    })

@app.route('/api/bots')
@login_required
def get_bots():
    """Get list of cloned bots (protected)"""
    return jsonify({
        'success': True,
        'bots': DUMMY_BOTS,
        'total': len(DUMMY_BOTS)
    })

@app.route('/api/login', methods=['POST'])
def login():
    """Login endpoint (demo - akan connect ke database nanti)"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    # Demo login (ganti dengan database check nanti)
    if username == 'admin' and password == 'admin123':
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'success': True, 'message': 'Login successful'})
    
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout endpoint"""
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out'})

@app.route('/api/check-auth')
def check_auth():
    """Check if user is authenticated"""
    if session.get('logged_in'):
        return jsonify({'authenticated': True, 'username': session.get('username')})
    return jsonify({'authenticated': False})

if __name__ == '__main__':
    print("🚀 Starting Flask server on http://localhost:9090")
    print("📁 Static files: /static/css/, /static/js/")
    print("📁 Templates: /templates/")
    app.run(host='0.0.0.0', port=9090, debug=True)