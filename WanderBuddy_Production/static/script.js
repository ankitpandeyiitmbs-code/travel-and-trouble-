// === 1. SCROLL REVEAL ANIMATIONS ===
// Checks if ScrollReveal is loaded (to prevent errors)
if (typeof ScrollReveal !== 'undefined') {
    const sr = ScrollReveal({
        origin: 'bottom',
        distance: '60px',
        duration: 2500,
        delay: 400,
        reset: true
    });

    sr.reveal('.hero-section h1', { delay: 200, origin: 'left' }); 
    sr.reveal('.hero-section p', { delay: 400, origin: 'right' }); 
    sr.reveal('.hero-section .btn-primary', { delay: 600, origin: 'bottom' }); 

    sr.reveal('.trip-card', { interval: 200 }); 
    sr.reveal('.stats-box', { origin: 'top', delay: 300 });
    sr.reveal('.review-card', { interval: 200, origin: 'left' });
    sr.reveal('.contact-card', { interval: 200 });
}

// === 2. TRIP FILTERING LOGIC ===
function filterTrips(category) {
    const cards = document.querySelectorAll('.trip-item');
    const buttons = document.querySelectorAll('.btn-group .btn');
    
    // Update Active Button Style
    buttons.forEach(btn => {
        btn.classList.remove('active', 'bg-primary');
        // Check if button text matches category or is 'All'
        if(btn.textContent.toLowerCase().includes(category) || (category === 'all' && btn.textContent === 'All')) {
            btn.classList.add('active', 'bg-primary');
        }
    });

    // Show/Hide Cards
    cards.forEach(card => {
        if (category === 'all' || card.classList.contains(category)) {
            card.style.display = 'block';
            // Simple fade-in animation
            card.style.opacity = '0';
            setTimeout(() => card.style.opacity = '1', 100);
        } else {
            card.style.display = 'none';
        }
    });
}

// === 3. NEWSLETTER ALERT (Footer) ===
const newsletterBtn = document.querySelector('.footer button');
if(newsletterBtn){
    newsletterBtn.addEventListener('click', function() {
        const input = document.querySelector('.footer input');
        if (input.value.includes('@')) {
            alert("Thanks for subscribing! 📩 Confirmation sent to: " + input.value);
            input.value = ""; 
        } else {
            alert("Please enter a valid email address.");
        }
    });
}