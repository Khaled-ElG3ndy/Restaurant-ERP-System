/** @odoo-module **/

const toneMap = {
    'أرضي':  'ground',
    'علوي':  'upper',
    'سفري':  'takeaway',
    'VIP':   'vip',
};

function applyFloorTone() {
    const floorMap = document.querySelector('.floor-map');
    if (!floorMap) return;

    // Try btn-primary first, then active class
    const activeBtn = document.querySelector('.floor-selector .btn-primary')
                   || document.querySelector('.floor-selector .button-floor.active');
    if (!activeBtn) return;

    // Get text content, strip any badge numbers (digits)
    const raw = Array.from(activeBtn.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE)
        .map(n => n.textContent.trim())
        .join('') || activeBtn.textContent.replace(/\d+/g, '').trim();

    const tone = toneMap[raw] || '';

    if (floorMap.getAttribute('data-pos-floor-tone') !== tone) {
        floorMap.setAttribute('data-pos-floor-tone', tone);
        console.log('[FloorTone] Applied tone:', tone, '← label:', raw);
    }
}

function startFloorToneWatcher() {
    // Apply immediately
    applyFloorTone();

    // Watch for class changes anywhere (catches Odoo re-renders & btn-primary swaps)
    const observer = new MutationObserver(() => applyFloorTone());
    observer.observe(document.body, {
        subtree: true,
        childList: true,
        attributes: true,
        attributeFilter: ['class'],
    });

    // Also catch direct clicks on floor tabs
    document.addEventListener('click', (e) => {
        if (e.target.closest('.floor-selector')) {
            setTimeout(applyFloorTone, 30);
            setTimeout(applyFloorTone, 150);
        }
    }, true);
}

// Wait for the POS DOM to be ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startFloorToneWatcher);
} else {
    startFloorToneWatcher();
}