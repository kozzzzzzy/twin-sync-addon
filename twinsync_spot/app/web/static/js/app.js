/* TwinSync Spot - Client-side JS */

// Get ingress path from page
const INGRESS_PATH = window.INGRESS_PATH || '';

// API helper
async function api(endpoint, options = {}) {
    const url = `${INGRESS_PATH}/api${endpoint}`;
    
    const response = await fetch(url, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    
    return response.json();
}

// Toast notifications
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container') || createToastContainer();
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="emoji">${type === 'success' ? '✅' : '❌'}</span>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 200);
    }, 3000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

// Loading state
function setLoading(element, loading) {
    if (loading) {
        element.disabled = true;
        element.dataset.originalText = element.innerHTML;
        element.innerHTML = '<span class="spinner" style="width:1rem;height:1rem;margin:0"></span>';
    } else {
        element.disabled = false;
        element.innerHTML = element.dataset.originalText;
    }
}

// =============================================================================
// SPOT ACTIONS
// =============================================================================

async function checkSpot(spotId, button) {
    setLoading(button, true);
    
    try {
        const result = await api(`/spots/${spotId}/check`, { method: 'POST' });
        showToast(`Check complete: ${result.status === 'sorted' ? 'All good!' : 'Needs attention'}`);
        
        // Refresh the page to show updated state
        location.reload();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(button, false);
    }
}

async function resetSpot(spotId, button) {
    setLoading(button, true);
    
    try {
        const result = await api(`/spots/${spotId}/reset`, { method: 'POST' });
        showToast(`Marked as sorted! Streak: ${result.current_streak} days 🔥`);
        location.reload();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(button, false);
    }
}

async function snoozeSpot(spotId, minutes, button) {
    setLoading(button, true);
    
    try {
        await api(`/spots/${spotId}/snooze`, {
            method: 'POST',
            body: JSON.stringify({ minutes }),
        });
        showToast(`Snoozed for ${minutes >= 60 ? Math.round(minutes/60) + ' hours' : minutes + ' minutes'} 💤`);
        location.reload();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(button, false);
    }
}

async function unsnoozeSpot(spotId, button) {
    setLoading(button, true);
    
    try {
        await api(`/spots/${spotId}/unsnooze`, { method: 'POST' });
        showToast('Spot unsnoozed!');
        location.reload();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(button, false);
    }
}

async function deleteSpot(spotId) {
    if (!confirm('Delete this spot? This cannot be undone.')) {
        return;
    }
    
    try {
        await api(`/spots/${spotId}`, { method: 'DELETE' });
        showToast('Spot deleted');
        location.href = INGRESS_PATH + '/';
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function checkAllSpots(button) {
    setLoading(button, true);
    
    try {
        const result = await api('/check-all', { method: 'POST' });
        const count = result.results.length;
        showToast(`Checked ${count} spot${count !== 1 ? 's' : ''}`);
        location.reload();
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(button, false);
    }
}

// =============================================================================
// ADD SPOT FORM
// =============================================================================

let spotTypes = [];
let voices = [];

async function initAddSpotForm() {
    // Load spot types and voices
    const [typesRes, voicesRes, camerasRes] = await Promise.all([
        api('/spot-types'),
        api('/voices'),
        api('/cameras'),
    ]);
    
    spotTypes = typesRes.types;
    voices = voicesRes.voices;
    
    // Populate camera select
    const cameraSelect = document.getElementById('camera-select');
    if (cameraSelect && camerasRes.cameras.length > 0) {
        cameraSelect.innerHTML = camerasRes.cameras.map(c => 
            `<option value="${c.entity_id}">${c.name}</option>`
        ).join('');
    } else if (cameraSelect) {
        cameraSelect.innerHTML = '<option value="">No cameras found</option>';
    }
    
    // Populate spot type select
    const typeSelect = document.getElementById('spot-type-select');
    if (typeSelect) {
        typeSelect.innerHTML = spotTypes.map(t => 
            `<option value="${t.value}">${t.label}</option>`
        ).join('');
        
        // Update definition template when type changes
        typeSelect.addEventListener('change', (e) => {
            const type = spotTypes.find(t => t.value === e.target.value);
            if (type) {
                document.getElementById('definition-input').value = type.template;
            }
        });
        
        // Set initial template
        const initialType = spotTypes.find(t => t.value === 'custom');
        if (initialType) {
            document.getElementById('definition-input').value = initialType.template;
        }
    }
    
    // Populate voice options
    const voiceContainer = document.getElementById('voice-options');
    if (voiceContainer) {
        voiceContainer.innerHTML = voices.filter(v => v.value !== 'custom').map(v => `
            <div class="voice-option ${v.value === 'supportive' ? 'selected' : ''}" 
                 data-value="${v.value}"
                 onclick="selectVoice('${v.value}')">
                <div class="emoji">${v.emoji}</div>
                <div class="name">${v.name}</div>
                <div class="desc">${v.description}</div>
            </div>
        `).join('');
    }
}

function selectVoice(value) {
    // Update UI
    document.querySelectorAll('.voice-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.value === value);
    });
    
    // Update hidden input
    const input = document.getElementById('voice-input');
    if (input) input.value = value;
}

async function submitAddSpotForm(event) {
    event.preventDefault();
    
    const form = event.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    setLoading(submitBtn, true);
    
    const data = {
        name: form.querySelector('#name-input').value,
        camera_entity: form.querySelector('#camera-select').value,
        spot_type: form.querySelector('#spot-type-select').value,
        definition: form.querySelector('#definition-input').value,
        voice: form.querySelector('#voice-input')?.value || 'supportive',
    };
    
    try {
        const result = await api('/spots', {
            method: 'POST',
            body: JSON.stringify(data),
        });
        
        showToast(`Spot "${result.spot.name}" created!`);
        location.href = INGRESS_PATH + '/';
    } catch (error) {
        showToast(error.message, 'error');
    } finally {
        setLoading(submitBtn, false);
    }
}

// =============================================================================
// WEBSOCKET FOR REAL-TIME UPDATES
// =============================================================================

let ws = null;

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}${INGRESS_PATH}/ws`;
    
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
        // Send ping every 30 seconds to keep alive
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 30000);
    };
    
    ws.onmessage = (event) => {
        if (event.data === 'pong') return;
        
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (e) {
            console.error('WebSocket message error:', e);
        }
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected, reconnecting...');
        setTimeout(connectWebSocket, 2000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'spot_updated':
            // Could update UI without full reload
            // For now, just show a toast
            console.log('Spot updated:', message.data);
            break;
            
        case 'check_started':
            showToast('Checking spot...', 'info');
            break;
            
        case 'check_complete':
            showToast('Check complete!');
            location.reload();
            break;
    }
}

// =============================================================================
// INIT
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Connect WebSocket for real-time updates
    connectWebSocket();
    
    // Initialize add spot form if on that page
    if (document.getElementById('add-spot-form')) {
        initAddSpotForm();
    }
});
