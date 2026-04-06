// static/js/script.js

// State Management
let currentPage = 'dashboard';
let isAuthenticated = false;
let currentUser = null;

// DOM Elements
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const contentWrapper = document.getElementById('contentWrapper');
const loginBtn = document.getElementById('loginBtn');
const logoutBtn = document.getElementById('logoutBtn');
const userInfo = document.getElementById('userInfo');
const usernameDisplay = document.getElementById('usernameDisplay');
const loginModal = document.getElementById('loginModal');
const botsLink = document.getElementById('botsLink');
const settingsLink = document.getElementById('settingsLink');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
    setupEventListeners();
    loadPage('dashboard');
});

// Event Listeners Setup
function setupEventListeners() {
    // Sidebar toggle
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', toggleSidebar);
    }
    
    // Navigation links
    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            if (page) {
                setActiveNavLink(link);
                loadPage(page);
            }
        });
    });
    
    // Login button
    if (loginBtn) {
        loginBtn.addEventListener('click', showLoginModal);
    }
    
    // Logout button
    if (logoutBtn) {
        logoutBtn.addEventListener('click', handleLogout);
    }
    
    // Login form
    const loginForm = document.getElementById('loginForm');
    if (loginForm) {
        loginForm.addEventListener('submit', handleLogin);
    }
    
    // Close modal on outside click
    window.addEventListener('click', (e) => {
        if (e.target === loginModal) {
            closeLoginModal();
        }
    });
}

// Toggle Sidebar
function toggleSidebar() {
    sidebar.classList.toggle('collapsed');
    
    // Save state to localStorage
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebarCollapsed', isCollapsed);
}

// Load collapsed state from localStorage
function loadSidebarState() {
    const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (isCollapsed) {
        sidebar.classList.add('collapsed');
    }
}

// Set Active Navigation Link
function setActiveNavLink(activeLink) {
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    activeLink.classList.add('active');
    currentPage = activeLink.dataset.page;
}

// Load Page Content
async function loadPage(page) {
    showLoading();
    
    switch(page) {
        case 'dashboard':
            await loadDashboard();
            break;
        case 'pricing':
            await loadPricing();
            break;
        case 'howto':
            loadHowTo();
            break;
        case 'bots':
            if (isAuthenticated) {
                await loadBots();
            } else {
                showLoginRequired();
            }
            break;
        case 'settings':
            if (isAuthenticated) {
                loadSettings();
            } else {
                showLoginRequired();
            }
            break;
        default:
            await loadDashboard();
    }
    
    hideLoading();
}

// Show Loading
function showLoading() {
    contentWrapper.innerHTML = `
        <div class="loading-spinner">
            <i class="fas fa-spinner fa-spin"></i>
                    <p>Memuat...</p>
                </div>
            `;
        }
        
        function hideLoading() {
            // Loading will be replaced by content
        }
        
        // Load Dashboard
        async function loadDashboard() {
            let statsHtml = `
                <div class="dashboard-grid">
                    <div class="stat-card">
                        <div class="stat-card-icon">
                            <i class="fas fa-users"></i>
                        </div>
                        <h3>Total Bot Active</h3>
                        <div class="stat-value">3</div>
                        <div class="stat-change">+2 minggu ini</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-card-icon">
                            <i class="fas fa-star"></i>
                        </div>
                        <h3>Total Stars Sold</h3>
                        <div class="stat-value">198,000</div>
                        <div class="stat-change">+12,500 hari ini</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-card-icon">
                            <i class="fas fa-chart-line"></i>
                        </div>
                        <h3>Total Volume (IDR)</h3>
                        <div class="stat-value">Rp53.4M</div>
                        <div class="stat-change">+Rp3.2M hari ini</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-card-icon">
                            <i class="fas fa-rocket"></i>
                        </div>
                        <h3>Total Users</h3>
                        <div class="stat-value">4,480</div>
                        <div class="stat-change">+124 hari ini</div>
                    </div>
                </div>
                
                <div class="pricing-container" style="margin-top: 30px;">
                    <div class="pricing-header">
                        <h2><i class="fas fa-chart-simple"></i> Statistik Cepat</h2>
                        <p>Ringkasan aktivitas bot dalam 7 hari terakhir</p>
                    </div>
                    <div style="padding: 24px; text-align: center;">
                        <canvas id="statsChart" style="max-height: 300px; width: 100%;"></canvas>
                    </div>
                </div>
            `;
            
            contentWrapper.innerHTML = statsHtml;
            
            // Load Chart.js for chart
            if (typeof Chart !== 'undefined') {
                loadChart();
            } else {
                // Dynamically load Chart.js
                const script = document.createElement('script');
                script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
                script.onload = () => loadChart();
                document.head.appendChild(script);
            }
        }
        
        function loadChart() {
            const ctx = document.getElementById('statsChart')?.getContext('2d');
            if (ctx) {
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: ['Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab', 'Min'],
                        datasets: [{
                            label: 'Stars Sold',
                            data: [12500, 18900, 15200, 22100, 19800, 24500, 31200],
                            borderColor: '#6366f1',
                            backgroundColor: 'rgba(99, 102, 241, 0.1)',
                            tension: 0.4,
                            fill: true
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {
                            legend: {
                                position: 'top',
                            }
                        }
                    }
                });
            }
        }
        
        // Load Pricing
        async function loadPricing() {
            try {
                const response = await fetch('/api/pricing');
                const data = await response.json();
                
                if (data.success) {
                    let pricingHtml = `
                        <div class="pricing-container">
                            <div class="pricing-header">
                                <h2><i class="fas fa-tag"></i> Daftar Harga Stars Telegram</h2>
                                <p>Minimal order: ${data.min_stars} stars | Maksimal: ${data.max_stars.toLocaleString()} stars</p>
                            </div>
                            <table class="pricing-table">
                                <thead>
                                    <tr>
                                        <th>Jumlah Stars</th>
                                        <th>Harga (IDR)</th>
                                        <th>Per Stars</th>
                                        <th>Diskon</th>
                                    </tr>
                                </thead>
                                <tbody>
                    `;
                    
                    data.pricing.forEach(item => {
                        const perStar = item.price / item.stars;
                        pricingHtml += `
                            <tr>
                                <td><strong>${item.stars.toLocaleString()}</strong> ⭐</td>
                                <td><strong>Rp${item.price.toLocaleString()}</strong></td>
                                <td>Rp${perStar.toFixed(0)}</td>
                                <td>${item.discount > 0 ? `<span class="discount-badge">${item.discount}% OFF</span>` : '-'}</td>
                            </tr>
                        `;
                    });
                    
                    pricingHtml += `
                                </tbody>
                            </table>
                        </div>
                        
                        <div style="margin-top: 24px; background: white; border-radius: 20px; padding: 24px;">
                            <h3><i class="fas fa-info-circle"></i> Informasi Pembelian</h3>
                            <p style="margin-top: 12px; color: var(--gray);">
                                ⭐ Stars akan dikirim langsung ke akun Telegram tujuan Anda.<br>
                                💰 Pembayaran via QRIS (otomatis) atau transfer bank.<br>
                                ⚡ Proses otomatis, stars akan masuk dalam hitungan detik setelah pembayaran terkonfirmasi.
                            </p>
                        </div>
                    `;
                    
                    contentWrapper.innerHTML = pricingHtml;
                }
            } catch (error) {
                console.error('Error loading pricing:', error);
                contentWrapper.innerHTML = '<div class="alert alert-error">Gagal memuat data harga</div>';
            }
        }
        
        // Load How To
        function loadHowTo() {
            const howtoHtml = `
                <div class="howto-grid">
                    <div class="howto-card">
                        <div class="howto-icon">
                            <i class="fas fa-robot"></i>
                        </div>
                        <h3>1. Clone Bot Telegram</h3>
                        <p>Buat bot Anda sendiri dengan sistem yang sama. Dapatkan token dari @BotFather, lalu clone melalui panel ini.</p>
                    </div>
                    <div class="howto-card">
                        <div class="howto-icon">
                            <i class="fas fa-key"></i>
                        </div>
                        <h3>2. Konfigurasi API</h3>
                        <p>Masukkan Fragment cookies, wallet mnemonic, dan konfigurasi lainnya untuk setiap bot secara terpisah.</p>
                    </div>
                    <div class="howto-card">
                        <div class="howto-icon">
                            <i class="fas fa-chart-line"></i>
                        </div>
                        <h3>3. Pantau Statistik</h3>
                        <p>Lihat performa bot Anda secara real-time: jumlah user, stars terjual, dan volume transaksi.</p>
                    </div>
                    <div class="howto-card">
                        <div class="howto-icon">
                            <i class="fas fa-coins"></i>
                        </div>
                        <h3>4. Atur Harga</h3>
                        <p>Sesuaikan harga per stars, buat template harga khusus, dan pilih metode perhitungan (per-star atau interpolasi).</p>
                    </div>
                    <div class="howto-card">
                        <div class="howto-icon">
                            <i class="fas fa-credit-card"></i>
                        </div>
                        <h3>5. Metode Deposit</h3>
                        <p>Konfigurasi rekening bank, QRIS manual, dan gateway pembayaran otomatis untuk deposit user.</p>
                    </div>
                    <div class="howto-card">
                        <div class="howto-icon">
                            <i class="fas fa-chart-simple"></i>
                        </div>
                        <h3>6. Export Data</h3>
                        <p>Export laporan transaksi, log aktivitas, dan statistik untuk keperluan analisis.</p>
                    </div>
                </div>
                
                <div style="margin-top: 30px; background: linear-gradient(135deg, var(--primary), var(--secondary)); border-radius: 20px; padding: 30px; color: white; text-align: center;">
                    <h3 style="margin-bottom: 10px;">💡 Butuh Bantuan?</h3>
                    <p style="opacity: 0.9;">Hubungi support kami di Telegram atau lihat dokumentasi lengkap.</p>
                    <button class="btn-primary" style="margin-top: 16px; background: white; color: var(--primary);" onclick="window.open('https://t.me/your_support', '_blank')">
                        <i class="fab fa-telegram"></i> Contact Support
                    </button>
                </div>
            `;
            
            contentWrapper.innerHTML = howtoHtml;
        }
        
        // Load Bots
        async function loadBots() {
            try {
                const response = await fetch('/api/bots');
                const data = await response.json();
                
                if (data.success && data.bots) {
                    let botsHtml = `
                        <div class="bots-header">
                            <h2><i class="fas fa-robot"></i> Bot Saya</h2>
                            <button class="btn-add" onclick="showAddBotModal()">
                                <i class="fas fa-plus"></i> Clone Bot Baru
                            </button>
                        </div>
                    `;
                    
                    data.bots.forEach(bot => {
                        botsHtml += `
                            <div class="bot-card">
                                <div class="bot-info">
                                    <div class="bot-avatar">
                                        <i class="fas fa-robot"></i>
                                    </div>
                                    <div class="bot-details">
                                        <h4>${bot.name}</h4>
                                        <p>${bot.username} • Dibuat: ${bot.created_at}</p>
                                        <p style="font-size: 0.75rem; margin-top: 4px;">
                                            👥 ${bot.users.toLocaleString()} users • ⭐ ${bot.stars_sold.toLocaleString()} stars
                                        </p>
                                    </div>
                                </div>
                                <div class="bot-status">
                                    <span class="status-badge ${bot.status === 'active' ? 'status-active' : 'status-inactive'}">
                                        ${bot.status === 'active' ? '● Online' : '● Offline'}
                                    </span>
                                    <div class="bot-actions">
                                        <button onclick="manageBot(${bot.id})" title="Kelola">
                                            <i class="fas fa-cog"></i>
                                        </button>
                                        <button onclick="viewBotStats(${bot.id})" title="Statistik">
                                            <i class="fas fa-chart-line"></i>
                                        </button>
                                        <button onclick="toggleBotStatus(${bot.id})" title="${bot.status === 'active' ? 'Stop' : 'Start'}">
                                            <i class="fas ${bot.status === 'active' ? 'fa-stop' : 'fa-play'}"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    
                    contentWrapper.innerHTML = botsHtml;
                }
            } catch (error) {
                console.error('Error loading bots:', error);
                contentWrapper.innerHTML = '<div class="alert alert-error">Gagal memuat daftar bot</div>';
            }
        }
        
        // Load Settings
        function loadSettings() {
            const settingsHtml = `
                <div style="background: white; border-radius: 20px; padding: 30px;">
                    <h2><i class="fas fa-cog"></i> Pengaturan Akun</h2>
                    <p style="color: var(--gray); margin-top: 8px;">Kelola preferensi dan konfigurasi akun Anda</p>
                    
                    <div style="margin-top: 30px;">
                        <div style="border-bottom: 1px solid var(--gray-light); padding: 20px 0;">
                            <h3><i class="fas fa-user"></i> Informasi Akun</h3>
                            <p><strong>Username:</strong> ${currentUser || 'admin'}</p>
                            <p><strong>Role:</strong> Administrator</p>
                            <p><strong>Member since:</strong> 2026-01-01</p>
                        </div>
                        
                        <div style="border-bottom: 1px solid var(--gray-light); padding: 20px 0;">
                            <h3><i class="fas fa-bell"></i> Notifikasi</h3>
                            <label style="display: flex; align-items: center; gap: 10px; margin-top: 10px;">
                                <input type="checkbox" checked> Email notifikasi untuk transaksi
                            </label>
                            <label style="display: flex; align-items: center; gap: 10px; margin-top: 10px;">
                                <input type="checkbox" checked> Notifikasi Telegram untuk bot offline
                            </label>
                        </div>
                        
                        <div style="padding: 20px 0;">
                            <h3><i class="fas fa-shield-alt"></i> Keamanan</h3>
                            <button class="btn-primary" style="margin-top: 10px;" onclick="alert('Fitur akan tersedia segera')">
                                <i class="fas fa-key"></i> Ubah Password
                            </button>
                            <button class="btn-primary" style="margin-top: 10px; margin-left: 10px; background: var(--gray);" onclick="alert('Fitur akan tersedia segera')">
                                <i class="fas fa-mobile-alt"></i> 2FA Authentication
                            </button>
                        </div>
                    </div>
                </div>
            `;
            
            contentWrapper.innerHTML = settingsHtml;
        }
        
        // Auth Functions
        async function checkAuthStatus() {
            try {
                const response = await fetch('/api/check-auth');
                const data = await response.json();
                
                if (data.authenticated) {
                    isAuthenticated = true;
                    currentUser = data.username;
                    updateUIForLoggedIn();
                } else {
                    isAuthenticated = false;
                    updateUIForLoggedOut();
                }
            } catch (error) {
                console.error('Error checking auth:', error);
                updateUIForLoggedOut();
            }
        }
        
        function updateUIForLoggedIn() {
            if (loginBtn) loginBtn.style.display = 'none';
            if (logoutBtn) logoutBtn.style.display = 'flex';
            if (userInfo) userInfo.style.display = 'flex';
            if (usernameDisplay) usernameDisplay.textContent = currentUser;
            if (botsLink) botsLink.style.display = 'flex';
            if (settingsLink) settingsLink.style.display = 'flex';
        }
        
        function updateUIForLoggedOut() {
            if (loginBtn) loginBtn.style.display = 'flex';
            if (logoutBtn) logoutBtn.style.display = 'none';
            if (userInfo) userInfo.style.display = 'none';
            if (botsLink) botsLink.style.display = 'none';
            if (settingsLink) settingsLink.style.display = 'none';
        }
        
        function showLoginModal() {
            loginModal.classList.add('show');
        }
        
        function closeLoginModal() {
            loginModal.classList.remove('show');
            document.getElementById('loginUsername').value = '';
            document.getElementById('loginPassword').value = '';
        }
        
        async function handleLogin(e) {
            e.preventDefault();
            
            const username = document.getElementById('loginUsername').value;
            const password = document.getElementById('loginPassword').value;
            
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ username, password })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    closeLoginModal();
                    await checkAuthStatus();
                    loadPage('dashboard');
                    showAlert('success', 'Login berhasil! Selamat datang kembali.');
                } else {
                    showAlert('error', data.message || 'Login gagal');
                }
            } catch (error) {
                console.error('Login error:', error);
                showAlert('error', 'Terjadi kesalahan, silakan coba lagi');
            }
        }
        
        async function handleLogout() {
            try {
                await fetch('/api/logout', { method: 'POST' });
                isAuthenticated = false;
                updateUIForLoggedOut();
                loadPage('dashboard');
                showAlert('success', 'Anda telah logout');
            } catch (error) {
                console.error('Logout error:', error);
            }
        }
        
        function showLoginRequired() {
            contentWrapper.innerHTML = `
                <div class="alert alert-error" style="text-align: center;">
                    <i class="fas fa-lock"></i> Silakan login terlebih dahulu untuk mengakses halaman ini
                </div>
            `;
        }
        
        function showAlert(type, message) {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type}`;
            alertDiv.innerHTML = `<i class="fas ${type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'}"></i> ${message}`;
            
            const container = document.querySelector('.content-wrapper');
            if (container) {
                container.insertBefore(alertDiv, container.firstChild);
                setTimeout(() => alertDiv.remove(), 3000);
            }
        }
        
        // Global functions for buttons
        window.showAddBotModal = function() {
            alert('Fitur clone bot akan tersedia segera.\n\nPersiapan:\n1. Buat bot di @BotFather\n2. Dapatkan token bot\n3. Masukkan token di form ini');
        };
        
        window.manageBot = function(botId) {
            alert(`Fitur manajemen untuk bot ID: ${botId}\n\nAkan tersedia:\n- Setting harga stars\n- Konfigurasi deposit (QRIS/Bank)\n- Lihat log transaksi\n- Start/Stop bot`);
        };
        
        window.viewBotStats = function(botId) {
            alert(`Menampilkan statistik lengkap untuk bot ID: ${botId}\n\nFitur akan segera hadir.`);
        };
        
        window.toggleBotStatus = function(botId) {
            alert(`Toggle status bot ID: ${botId}\n\nFitur akan segera hadir.`);
        };
        
        // Load sidebar state on init
        loadSidebarState();
        
        // Expose functions globally
        window.closeLoginModal = closeLoginModal;
        window.showLoginModal = showLoginModal;
        window.handleLogin = handleLogin;
        window.handleLogout = handleLogout;