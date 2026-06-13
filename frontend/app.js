/**
 * CommerceBot — Chat Application Logic
 * Handles chat messages, product cards, comparison, and Stripe checkout.
 */

const API_BASE = window.location.origin;
let conversationId = null;
let compareList = [];

// ═══════════════════════════════════════════════════════════════
// Initialization
// ═══════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('chatInput').focus();
    updateCompareBar();
    refreshKPIs();
    setInterval(refreshKPIs, 30000); // Refresh KPIs every 30s
});

// ═══════════════════════════════════════════════════════════════
// Chat Functions
// ═══════════════════════════════════════════════════════════════

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

async function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();
    if (!message) return;

    // Disable send button
    const sendButton = document.getElementById('sendButton');
    sendButton.disabled = true;
    input.value = '';
    input.style.height = 'auto';

    // Add user message to chat
    appendMessage('user', escapeHtml(message));
    showTypingIndicator();

    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                conversation_id: conversationId,
            }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Request failed');
        }

        const data = await response.json();
        conversationId = data.conversation_id;

        // Remove typing indicator
        removeTypingIndicator();

        // Render response
        renderResponse(data);

    } catch (error) {
        removeTypingIndicator();
        appendMessage('assistant',
            `❌ Sorry, something went wrong: ${escapeHtml(error.message)}. Please try again.`);
    }

    sendButton.disabled = false;
    input.focus();
}

function sendQuick(message) {
    document.getElementById('chatInput').value = message;
    sendMessage();
}

function newConversation() {
    conversationId = null;
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = `
        <div class="message assistant">
            <div class="message-avatar">🤖</div>
            <div class="message-content">
                <p>Starting a new conversation! 👋 What would you like to shop for?</p>
                <div class="quick-actions">
                    <span class="quick-label">Try asking:</span>
                    <button class="quick-btn" onclick="sendQuick('Show me laptops under $1500')">
                        Show me laptops under $1500
                    </button>
                    <button class="quick-btn" onclick="sendQuick('What headphones do you have?')">
                        What headphones do you have?
                    </button>
                    <button class="quick-btn" onclick="sendQuick('Recommend some programming books')">
                        Recommend some programming books
                    </button>
                </div>
            </div>
        </div>
    `;
    compareList = [];
    updateCompareBar();
}

// ═══════════════════════════════════════════════════════════════
// Response Rendering
// ═══════════════════════════════════════════════════════════════

function renderResponse(data) {
    let content = '';

    // Add text response with product references
    if (data.message) {
        content += formatMessage(data.message);
    }

    // Add product cards if products were returned
    if (data.products && data.products.length > 0) {
        content += renderProductCards(data.products);
    }

    // Add comparison if available
    if (data.comparison && data.comparison.products && data.comparison.products.length >= 2) {
        content += renderComparison(data.comparison);
    }

    // Add checkout link if available
    if (data.checkout_url) {
        content += `
            <div style="margin-top:12px; padding:12px; background:rgba(0,200,83,0.1);
                        border:1px solid var(--success); border-radius:8px;">
                <p>✅ <strong>Checkout ready!</strong></p>
                <a href="${escapeHtml(data.checkout_url)}" target="_blank"
                   style="display:inline-block; margin-top:8px; padding:10px 24px;
                          background:var(--success); color:#000; text-decoration:none;
                          border-radius:8px; font-weight:600;">
                    💳 Proceed to Secure Checkout
                </a>
            </div>
        `;
    }

    // Add error if any
    if (data.error) {
        content += `<p style="color: var(--text-muted); font-size: 0.82rem;">
            ⚠️ Note: ${escapeHtml(data.error)}</p>`;
    }

    appendMessage('assistant', content, true);
}

function formatMessage(text) {
    // Replace [PRODUCT:id] markers with product card placeholders
    // (actual product cards are rendered separately)
    let formatted = escapeHtml(text);

    // Bold markdown-style formatting
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // Line breaks
    formatted = formatted.replace(/\n/g, '<br>');

    return `<p>${formatted}</p>`;
}

function renderProductCards(products) {
    let html = '<div class="product-card-list">';
    for (const product of products) {
        const isSelected = compareList.includes(product.id);
        html += `
            <div class="product-card" id="product-card-${escapeHtml(product.id)}">
                <div class="product-card-header">
                    <span class="product-card-name">${escapeHtml(product.name)}</span>
                    <span class="product-card-price">$${product.price.toFixed(2)}</span>
                </div>
                <p class="product-card-desc">${escapeHtml(product.description.substring(0, 150))}...</p>
                <div class="product-card-meta">
                    <span>⭐ ${product.rating}/5</span>
                    <span>📦 Stock: ${product.stock}</span>
                    <span>🏷️ ${escapeHtml(product.category)}</span>
                </div>
                <div class="product-card-actions">
                    <button class="btn-compare ${isSelected ? 'selected' : ''}"
                            onclick="toggleCompare('${escapeHtml(product.id)}', this)" title="Add to comparison">
                        ${isSelected ? '✓ Compare' : '⇆ Compare'}
                    </button>
                    <button class="btn-details"
                            onclick="showProductDetails('${escapeHtml(product.id)}')" title="View details">
                        📋 Details
                    </button>
                    <button class="btn-buy"
                            onclick="buyProduct('${escapeHtml(product.id)}')" title="Buy now">
                        💳 Buy Now
                    </button>
                </div>
            </div>
        `;
    }
    html += '</div>';
    return html;
}

function renderComparison(comparison) {
    const products = comparison.products;
    const specs = comparison.specs_comparison || {};
    const rec = comparison.recommendation || {};

    let html = '<div class="comparison-container">';
    html += '<h4 style="margin-bottom: 12px;">📊 Product Comparison</h4>';

    // Build comparison table
    html += '<table class="comparison-table"><thead><tr>';
    html += '<th>Specification</th>';
    for (const p of products) {
        html += `<th>${escapeHtml(p.name.substring(0, 20))}<br><small>$${p.price.toFixed(2)}</small></th>`;
    }
    html += '</tr></thead><tbody>';

    for (const [specKey, specValues] of Object.entries(specs)) {
        html += '<tr>';
        html += `<td><strong>${escapeHtml(specKey)}</strong></td>`;
        for (const p of products) {
            html += `<td>${escapeHtml(String(specValues[p.id] || 'N/A'))}</td>`;
        }
        html += '</tr>';
    }
    html += '</tbody></table>';

    // Recommendation
    if (rec.best_value_id) {
        html += `
            <div class="comparison-best-value">
                💡 <strong>Best Value:</strong> ${escapeHtml(rec.best_value)} at $${rec.best_value_price?.toFixed(2)}
                <br>🏆 <strong>Best Rated:</strong> ${escapeHtml(rec.best_rated)} (${rec.best_rated_rating}/5)
            </div>
        `;
    }

    html += '</div>';
    return html;
}

// ═══════════════════════════════════════════════════════════════
// Chat UI Helpers
// ═══════════════════════════════════════════════════════════════

function appendMessage(role, content, isHtml = false) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatar = role === 'user' ? '👤' : '🤖';
    div.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">${isHtml ? content : `<p>${content}</p>`}</div>
    `;

    container.appendChild(div);
    scrollToBottom();
}

function showTypingIndicator() {
    const container = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant';
    typingDiv.id = 'typingIndicator';
    typingDiv.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    container.appendChild(typingDiv);
    scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

function scrollToBottom() {
    const container = document.getElementById('chatMessages');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 50);
}

// ═══════════════════════════════════════════════════════════════
// Product Interactions
// ═══════════════════════════════════════════════════════════════

function toggleCompare(productId, button) {
    const index = compareList.indexOf(productId);
    if (index > -1) {
        compareList.splice(index, 1);
        button.classList.remove('selected');
        button.textContent = '⇆ Compare';
    } else {
        if (compareList.length >= 4) {
            alert('You can compare up to 4 products at a time.');
            return;
        }
        compareList.push(productId);
        button.classList.add('selected');
        button.textContent = '✓ Compare';
    }
    updateCompareBar();
}

function updateCompareBar() {
    let bar = document.getElementById('compareBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'compareBar';
        bar.className = 'compare-bar';
        bar.innerHTML = `
            <span id="compareCount"></span>
            <button class="btn-compare-now" onclick="compareNow()">Compare Now</button>
            <button style="background:none;border:none;color:var(--text-muted);cursor:pointer"
                    onclick="clearCompare()">Clear</button>
        `;
        document.body.appendChild(bar);
    }

    if (compareList.length >= 2) {
        bar.classList.add('visible');
        document.getElementById('compareCount').textContent =
            `Comparing ${compareList.length} product${compareList.length > 1 ? 's' : ''}`;
    } else {
        bar.classList.remove('visible');
    }
}

function compareNow() {
    if (compareList.length < 2) return;
    const message = `Compare products: ${compareList.join(', ')}`;
    document.getElementById('chatInput').value = message;
    sendMessage();
    compareList = [];
    updateCompareBar();
}

function clearCompare() {
    compareList = [];
    // Reset all compare buttons
    document.querySelectorAll('.btn-compare').forEach(btn => {
        btn.classList.remove('selected');
        btn.textContent = '⇆ Compare';
    });
    updateCompareBar();
}

function showProductDetails(productId) {
    const panel = document.getElementById('detailPanel');
    const content = document.getElementById('detailContent');

    fetch(`${API_BASE}/products/${productId}`)
        .then(r => r.json())
        .then(product => {
            content.innerHTML = `
                <div style="text-align:center; margin-bottom:16px;">
                    <img src="${escapeHtml(product.image_url)}"
                         alt="${escapeHtml(product.name)}"
                         style="max-width:100%; border-radius:8px;"
                         onerror="this.style.display='none'">
                </div>
                <div class="detail-product-name">${escapeHtml(product.name)}</div>
                <div class="detail-product-price">$${product.price.toFixed(2)}</div>
                <div class="detail-product-desc">${escapeHtml(product.description)}</div>
                ${product.specs ? `
                    <ul class="detail-specs">
                        ${Object.entries(product.specs).map(([k, v]) => `
                            <li>
                                <span class="spec-key">${escapeHtml(k)}</span>
                                <span class="spec-value">${escapeHtml(String(v))}</span>
                            </li>
                        `).join('')}
                    </ul>
                ` : ''}
                <div style="margin-top: 12px; font-size: 0.85rem; color: var(--text-muted);">
                    📦 Stock: ${product.stock} | ⭐ Rating: ${product.rating}/5 | 🏷️ ${escapeHtml(product.category)}
                </div>
                <button class="detail-buy-btn" onclick="buyProduct('${escapeHtml(product.id)}')">
                    💳 Buy Now — $${product.price.toFixed(2)}
                </button>
            `;
            panel.style.display = 'flex';
        })
        .catch(err => {
            content.innerHTML = `<p>Error loading product details: ${escapeHtml(err.message)}</p>`;
            panel.style.display = 'flex';
        });
}

function closeDetails() {
    document.getElementById('detailPanel').style.display = 'none';
}

// ═══════════════════════════════════════════════════════════════
// Checkout
// ═══════════════════════════════════════════════════════════════

async function buyProduct(productId) {
    try {
        const response = await fetch(`${API_BASE}/checkout`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_id: productId,
                quantity: 1,
                conversation_id: conversationId,
            }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Checkout failed');
        }

        const data = await response.json();

        // Add checkout message to chat
        appendMessage('assistant', `
            ✅ <strong>Checkout ready for ${escapeHtml(data.product_name)}!</strong><br>
            Amount: <strong>$${data.amount.toFixed(2)}</strong><br>
            Click below to complete your purchase securely via Stripe.
        `, true);

        // Open checkout in new window
        if (data.checkout_url) {
            window.open(data.checkout_url, '_blank');
        }

    } catch (error) {
        appendMessage('assistant',
            `❌ Checkout failed: ${escapeHtml(error.message)}`);
    }
}

// ═══════════════════════════════════════════════════════════════
// KPI Refresh
// ═══════════════════════════════════════════════════════════════

async function refreshKPIs() {
    try {
        const response = await fetch(`${API_BASE}/metrics`);
        if (!response.ok) return;
        const data = await response.json();

        document.getElementById('kpi-conversations').textContent = data.total_conversations || '0';
        document.getElementById('kpi-orders').textContent = data.completed_orders || '0';
        document.getElementById('kpi-conversion').textContent =
            `${data.conversion_rate?.toFixed(1) || '0'}%`;
        document.getElementById('kpi-revenue').textContent =
            `$${(data.total_revenue || 0).toFixed(0)}`;
    } catch (e) {
        // Silently fail — KPI refresh is non-critical
    }
}

// ═══════════════════════════════════════════════════════════════
// Utilities
// ═══════════════════════════════════════════════════════════════

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Auto-resize textarea
document.addEventListener('input', function(e) {
    if (e.target.id === 'chatInput') {
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
    }
});
