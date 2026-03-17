// js/script.js
class FragmentStarsApp {
    constructor() {
        this.config = {
            pricePerStar: 0.02,
            minStars: 10,
            maxStars: 100000,
            apiEndpoint: 'https://caused-fifteen-ssl-pci.trycloudflare.com', // Ganti dengan endpoint bot Anda
            botUsername: 'autofragmentbot' // Ganti dengan username bot Anda
        };

        this.state = {
            currentStars: 100,
            showSender: true,
            isProcessing: false
        };

        this.init();
    }

    init() {
        this.cacheElements();
        this.attachEvents();
        this.updatePrice();
        this.initModals();
        this.initMobileMenu();
    }

    cacheElements() {
        // Modal elements
        this.purchaseModal = document.getElementById('purchaseModal');
        this.successModal = document.getElementById('successModal');
        this.closeModalBtn = document.getElementById('closeModal');
        this.closeSuccessModal = document.getElementById('closeSuccessModal');
        
        // Form elements
        this.purchaseForm = document.getElementById('purchaseForm');
        this.usernameInput = document.getElementById('username');
        this.starsInput = document.getElementById('stars');
        this.quickStarBtns = document.querySelectorAll('.quick-star');
        this.senderRadios = document.querySelectorAll('input[name="showSender"]');
        
        // Display elements
        this.pricePerStarEl = document.getElementById('pricePerStar');
        this.starsQuantityEl = document.getElementById('starsQuantity');
        this.totalPriceEl = document.getElementById('totalPrice');
        
        // Buttons
        this.buyNowBtn = document.getElementById('buyNowBtn');
        this.howItWorksBtn = document.getElementById('howItWorksBtn');
        this.pricingBtns = document.querySelectorAll('.pricing-btn');
        this.viewTransactionBtn = document.getElementById('viewTransaction');
        this.newPurchaseBtn = document.getElementById('newPurchase');
        
        // Contact buttons
        this.contactBtns = document.querySelectorAll('#contactBtn, #mobileContactBtn, #footerContactBtn');
        
        // Mobile menu
        this.mobileMenuBtn = document.getElementById('mobileMenuBtn');
        this.mobileMenu = document.getElementById('mobileMenu');
    }

    attachEvents() {
        // Purchase flow
        this.buyNowBtn?.addEventListener('click', () => this.openPurchaseModal());
        this.pricingBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const stars = e.currentTarget.dataset.stars;
                this.openPurchaseModal(parseInt(stars));
            });
        });

        // Form events
        this.purchaseForm?.addEventListener('submit', (e) => this.handlePurchase(e));
        this.starsInput?.addEventListener('input', () => this.handleStarsInput());
        this.quickStarBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const stars = parseInt(e.currentTarget.dataset.stars);
                this.setStars(stars);
            });
        });

        this.senderRadios.forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.state.showSender = e.target.value === 'true';
            });
        });

        // Modal close events
        this.closeModalBtn?.addEventListener('click', () => this.closeModal(this.purchaseModal));
        this.closeSuccessModal?.addEventListener('click', () => this.closeModal(this.successModal));
        
        window.addEventListener('click', (e) => {
            if (e.target === this.purchaseModal) this.closeModal(this.purchaseModal);
            if (e.target === this.successModal) this.closeModal(this.successModal);
        });

        // Navigation
        this.howItWorksBtn?.addEventListener('click', () => {
            document.getElementById('how-it-works').scrollIntoView({ behavior: 'smooth' });
        });

        this.viewTransactionBtn?.addEventListener('click', () => {
            const txHash = this.viewTransactionBtn.dataset.txHash;
            if (txHash) {
                window.open(`https://tonviewer.com/transaction/${txHash}`, '_blank');
            }
        });

        this.newPurchaseBtn?.addEventListener('click', () => {
            this.closeModal(this.successModal);
            this.openPurchaseModal();
        });

        // Contact buttons
        this.contactBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                window.open(`https://t.me/${this.config.botUsername}`, '_blank');
            });
        });

        // Mobile menu
        this.mobileMenuBtn?.addEventListener('click', () => this.toggleMobileMenu());
        
        // Close mobile menu when clicking a link
        this.mobileMenu?.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                this.mobileMenu.classList.remove('active');
            });
        });
    }

    initModals() {
        // Set initial price per star
        this.pricePerStarEl.textContent = `${this.config.pricePerStar} TON`;
    }

    initMobileMenu() {
        // Close mobile menu on window resize if open
        window.addEventListener('resize', () => {
            if (window.innerWidth > 968) {
                this.mobileMenu?.classList.remove('active');
            }
        });
    }

    toggleMobileMenu() {
        this.mobileMenu?.classList.toggle('active');
    }

    openPurchaseModal(stars = 100) {
        this.resetForm();
        if (stars) {
            this.setStars(stars);
        }
        this.purchaseModal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    closeModal(modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }

    resetForm() {
        this.usernameInput.value = '';
        this.setStars(100);
        document.querySelector('input[name="showSender"][value="true"]').checked = true;
        this.state.showSender = true;
    }

    setStars(stars) {
        this.starsInput.value = stars;
        this.state.currentStars = stars;
        this.updatePrice();
    }

    handleStarsInput() {
        let stars = parseInt(this.starsInput.value) || 0;
        
        // Validate range
        if (stars < this.config.minStars) {
            stars = this.config.minStars;
            this.starsInput.value = stars;
        } else if (stars > this.config.maxStars) {
            stars = this.config.maxStars;
            this.starsInput.value = stars;
        }
        
        this.state.currentStars = stars;
        this.updatePrice();
    }

    updatePrice() {
        const total = this.state.currentStars * this.config.pricePerStar;
        this.starsQuantityEl.textContent = this.state.currentStars.toLocaleString();
        this.totalPriceEl.textContent = `${total.toFixed(2)} TON`;
    }

    async handlePurchase(e) {
        e.preventDefault();

        if (this.state.isProcessing) return;

        // Validate username
        const username = this.usernameInput.value.trim();
        if (!username) {
            this.showToast('Error', 'Please enter a username', 'error');
            return;
        }

        // Validate stars
        const stars = parseInt(this.starsInput.value);
        if (isNaN(stars) || stars < this.config.minStars || stars > this.config.maxStars) {
            this.showToast('Error', `Stars must be between ${this.config.minStars} and ${this.config.maxStars}`, 'error');
            return;
        }

        // Show processing state
        this.state.isProcessing = true;
        const submitBtn = document.getElementById('submitPurchase');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        submitBtn.disabled = true;

        try {
            // Here you would make an API call to your bot
            // For now, we'll simulate a successful purchase
            await this.simulatePurchase({
                username: username.replace('@', ''),
                stars: stars,
                showSender: this.state.showSender
            });

            // Show success modal
            this.closeModal(this.purchaseModal);
            this.showSuccessModal({
                username: username.replace('@', ''),
                stars: stars,
                txHash: 'simulated_tx_hash_' + Date.now()
            });

        } catch (error) {
            this.showToast('Error', error.message || 'Purchase failed', 'error');
        } finally {
            // Reset button state
            this.state.isProcessing = false;
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    }

    async simulatePurchase(data) {
        // Simulate API call
        return new Promise((resolve) => {
            setTimeout(() => {
                console.log('Purchase data:', data);
                resolve({ success: true });
            }, 2000);
        });
    }

    showSuccessModal(data) {
        const details = document.getElementById('transactionDetails');
        details.innerHTML = `
            <div>Recipient: @${data.username}</div>
            <div>Stars: ${data.stars.toLocaleString()}</div>
            <div>Transaction: ${data.txHash}</div>
        `;
        
        this.viewTransactionBtn.dataset.txHash = data.txHash;
        this.successModal.classList.add('active');
    }

    showToast(title, message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle'}"></i>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close"><i class="fas fa-times"></i></button>
        `;

        document.body.appendChild(toast);

        // Auto remove after 5 seconds
        setTimeout(() => {
            toast.remove();
        }, 5000);

        // Close button
        toast.querySelector('.toast-close').addEventListener('click', () => {
            toast.remove();
        });
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new FragmentStarsApp();
});
