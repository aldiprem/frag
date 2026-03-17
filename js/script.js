// js/script.js
class FragmentStarsApp {
    constructor() {
        this.config = {
            pricePerStar: 0.02,
            minStars: 50,
            maxStars: 100000,
            apiEndpoint: 'https://caused-fifteen-ssl-pci.trycloudflare.com',
            botUsername: 'autofragmentbot'
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
            // ============= PANGGILAN API NYATA KE BACKEND =============
            console.log('Sending purchase request...', {
                username: username.replace('@', ''),
                stars: stars,
                show_sender: this.state.showSender
            });

            // Panggil endpoint backend
            const response = await fetch(`${this.config.apiUrl}/purchase`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username: username.replace('@', ''),
                    stars: stars,
                    show_sender: this.state.showSender
                })
            });

            // Parse response
            const result = await response.json();
            console.log('Purchase response:', result);

            if (!response.ok) {
                throw new Error(result.error || `HTTP error! status: ${response.status}`);
            }

            if (result.success) {
                // Success - tampilkan modal dengan tx hash NYATA
                this.closeModal(this.purchaseModal);
                this.showSuccessModal({
                    username: username.replace('@', ''),
                    stars: stars,
                    txHash: result.tx_hash,  // Hash NYATA dari blockchain
                    recipient: result.recipient || username.replace('@', '')
                });
                
                this.showToast('Success', 'Purchase completed successfully!', 'success');
            } else {
                // Backend mengembalikan success: false
                throw new Error(result.error || 'Purchase failed');
            }

        } catch (error) {
            console.error('Purchase error:', error);
            
            // Tampilkan error ke user
            let errorMessage = error.message || 'Purchase failed';
            
            // Handle specific error cases
            if (errorMessage.includes('Failed to fetch') || errorMessage.includes('NetworkError')) {
                errorMessage = 'Cannot connect to server. Please check your connection or try again later.';
            } else if (errorMessage.includes('User not found')) {
                errorMessage = 'Username not found on Fragment. Please check and try again.';
            } else if (errorMessage.includes('insufficient balance')) {
                errorMessage = 'Insufficient wallet balance. Please top up your wallet.';
            }
            
            this.showToast('Error', errorMessage, 'error');
            
        } finally {
            // Reset button state
            this.state.isProcessing = false;
            submitBtn.innerHTML = originalText;
            submitBtn.disabled = false;
        }
    }

    showSuccessModal(data) {
        const details = document.getElementById('transactionDetails');
        details.innerHTML = `
            <div><strong>Recipient:</strong> @${data.username}</div>
            <div><strong>Stars:</strong> ${data.stars.toLocaleString()}</div>
            <div><strong>Transaction Hash:</strong></div>
            <div style="font-size: 12px; word-break: break-all; background: #1a1a1a; padding: 8px; border-radius: 4px; margin-top: 4px;">${data.txHash}</div>
        `;
        
        // Set transaction hash untuk tombol view
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
