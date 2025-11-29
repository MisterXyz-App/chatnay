// JavaScript untuk fitur chat real-time yang ditingkatkan
class ChatManager {
    constructor() {
        this.currentChatUserId = null;
        this.lastMessageId = 0;
        this.isPolling = false;
        this.pollInterval = null;
        this.typingTimer = null;
        this.isTyping = false;
        this.messageQueue = [];
        this.isProcessingQueue = false;
    }

    startChat(userId) {
        this.currentChatUserId = userId;
        this.lastMessageId = 0;
        this.stopPolling(); // Stop previous polling
        this.startPolling();
        this.scrollToBottom();
        
        // Update unread counts
        this.updateUnreadCounts();
    }

    stopChat() {
        this.stopPolling();
        this.currentChatUserId = null;
    }

    async sendMessage(formData) {
        try {
            const sendButton = document.getElementById('send-button');
            const messageInput = document.getElementById('message-input');
            
            // Disable form while sending
            sendButton.disabled = true;
            sendButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            messageInput.disabled = true;

            // Show upload progress if file is attached
            const fileInput = document.getElementById('file-upload');
            if (fileInput && fileInput.files.length > 0) {
                this.showUploadProgress();
            }

            const response = await fetch('/send_message', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            // Re-enable form
            sendButton.disabled = false;
            sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
            messageInput.disabled = false;
            this.hideUploadProgress();
            
            return result;
        } catch (error) {
            console.error('Error sending message:', error);
            
            // Re-enable form on error
            const sendButton = document.getElementById('send-button');
            const messageInput = document.getElementById('message-input');
            sendButton.disabled = false;
            sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
            messageInput.disabled = false;
            this.hideUploadProgress();
            
            return { success: false, error: 'Network error' };
        }
    }

    async fetchMessages() {
        if (!this.currentChatUserId || this.isPolling) return;

        this.isPolling = true;
        
        try {
            // Add cache busting parameter
            const response = await fetch(`/get_messages/${this.currentChatUserId}?last_message_id=${this.lastMessageId}&_=${Date.now()}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const result = await response.json();
            
            if (result.success && result.messages && result.messages.length > 0) {
                // Add messages to queue for processing
                this.messageQueue.push(...result.messages);
                this.lastMessageId = Math.max(this.lastMessageId, ...result.messages.map(m => m.id));
                
                // Process queue if not already processing
                if (!this.isProcessingQueue) {
                    this.processMessageQueue();
                }
                
                // Play notification sound for new messages from other users
                const newMessagesFromOthers = result.messages.filter(msg => 
                    msg.sender_id !== currentUserId && !document.querySelector(`[data-message-id="${msg.id}"]`)
                );
                
                if (newMessagesFromOthers.length > 0) {
                    this.playNotificationSound();
                    this.updateUnreadCounts();
                    
                    // Show desktop notification if supported
                    if (this.shouldShowDesktopNotification()) {
                        this.showDesktopNotification(newMessagesFromOthers[0]);
                    }
                }
            }
        } catch (error) {
            console.error('Error fetching messages:', error);
            this.handleConnectionError();
        } finally {
            this.isPolling = false;
        }
    }

    processMessageQueue() {
        if (this.isProcessingQueue || this.messageQueue.length === 0) return;
        
        this.isProcessingQueue = true;
        
        // Process messages in batches for better performance
        const batchSize = 10;
        const messagesToProcess = this.messageQueue.splice(0, batchSize);
        
        const chatContainer = document.getElementById('chat-messages');
        const wasAtBottom = this.isAtBottom();
        
        messagesToProcess.forEach(message => {
            // Check if message already exists
            if (!document.querySelector(`[data-message-id="${msg.id}"]`)) {
                const messageElement = this.createMessageElement(message);
                
                // Use requestAnimationFrame for smooth rendering
                requestAnimationFrame(() => {
                    chatContainer.appendChild(messageElement);
                    
                    // Add subtle animation for new messages
                    messageElement.style.opacity = '0';
                    messageElement.style.transform = 'translateY(10px)';
                    
                    requestAnimationFrame(() => {
                        messageElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                        messageElement.style.opacity = '1';
                        messageElement.style.transform = 'translateY(0)';
                    });
                });
            }
        });
        
        // Scroll to bottom if user was at bottom
        if (wasAtBottom) {
            requestAnimationFrame(() => {
                this.scrollToBottom();
            });
        }
        
        // Continue processing if there are more messages
        if (this.messageQueue.length > 0) {
            setTimeout(() => {
                this.isProcessingQueue = false;
                this.processMessageQueue();
            }, 50); // Small delay to prevent blocking the UI
        } else {
            this.isProcessingQueue = false;
        }
    }

    createMessageElement(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `mb-4 message-item ${message.sender_id === currentUserId ? 'text-right' : ''}`;
        messageDiv.setAttribute('data-message-id', message.id);
        
        const isSent = message.sender_id === currentUserId;
        
        let content = '';
        
        // Message header for received messages
        if (!isSent) {
            content += `
                <div class="flex items-center space-x-2 mb-1">
                    <img src="${message.sender_profile_pic}" alt="${message.sender_username}" 
                         class="w-5 h-5 rounded-full object-cover">
                    <span class="text-xs text-gray-600 font-medium">${message.sender_username}</span>
                </div>
            `;
        }
        
        // Media content
        if (message.media_url) {
            if (message.media_type === 'image') {
                content += `
                    <div class="mb-2">
                        <img src="${message.media_url}" alt="Gambar" 
                             class="max-w-full md:max-w-sm rounded-lg cursor-pointer transition-transform duration-200 hover:scale-105" 
                             onclick="chatManager.openMedia('${message.media_url}', 'image')"
                             loading="lazy">
                    </div>
                `;
            } else if (message.media_type === 'video') {
                content += `
                    <div class="mb-2">
                        <video controls class="max-w-full md:max-w-sm rounded-lg" preload="metadata">
                            <source src="${message.media_url}" type="video/mp4">
                            Browser Anda tidak mendukung video.
                        </video>
                    </div>
                `;
            } else {
                content += `
                    <div class="mb-2">
                        <a href="${message.media_url}" target="_blank" 
                           class="inline-flex items-center space-x-2 px-3 py-2 bg-gray-100 rounded-lg hover:bg-gray-200 transition duration-150 text-sm">
                            <i class="fas fa-file-download text-blue-500"></i>
                            <span class="font-medium">Download File</span>
                        </a>
                    </div>
                `;
            }
        }
        
        // Text content
        if (message.content) {
            content += `
                <div class="message-content break-words text-sm">
                    ${this.urlize(message.content)}
                </div>
            `;
        }
        
        // Message footer
        let deleteButton = '';
        if (isSent || currentUserIsAdmin) {
            deleteButton = `
                <button onclick="chatManager.deleteMessage(${message.id})" 
                        class="text-red-400 hover:text-red-600 transition duration-150 ml-2 opacity-0 group-hover:opacity-100"
                        title="Hapus pesan">
                    <i class="fas fa-trash text-xs"></i>
                </button>
            `;
        }
        
        content += `
            <div class="flex items-center justify-between mt-1 text-xs opacity-75">
                <span class="message-time">${message.timestamp}</span>
                <div class="flex items-center space-x-1">
                    ${message.is_read && isSent ? 
                        '<i class="fas fa-check-double text-blue-400" title="Telah dibaca"></i>' : 
                        (!message.is_read && isSent ? '<i class="fas fa-check text-gray-400" title="Terkirim"></i>' : '')
                    }
                    ${deleteButton}
                </div>
            </div>
        `;
        
        messageDiv.innerHTML = `
            <div class="inline-block max-w-xs lg:max-w-md group">
                <div class="message-bubble rounded-2xl p-3 ${isSent ? 'sent' : 'received'} shadow-sm">
                    ${content}
                </div>
            </div>
        `;
        
        return messageDiv;
    }

    urlize(text) {
        const urlRegex = /(https?:\/\/[^\s]+)/g;
        return text.replace(urlRegex, '<a href="$1" target="_blank" class="text-blue-600 hover:text-blue-800 underline break-all">$1</a>');
    }

    scrollToBottom() {
        const chatContainer = document.getElementById('chat-messages');
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }

    scrollToBottomSmooth() {
        const chatContainer = document.getElementById('chat-messages');
        if (chatContainer) {
            chatContainer.scrollTo({
                top: chatContainer.scrollHeight,
                behavior: 'smooth'
            });
        }
    }

    isAtBottom() {
        const chatContainer = document.getElementById('chat-messages');
        if (!chatContainer) return true;
        
        const threshold = 100; // pixels from bottom
        return chatContainer.scrollTop + chatContainer.clientHeight >= chatContainer.scrollHeight - threshold;
    }

    startPolling() {
        // Clear any existing interval
        this.stopPolling();
        
        // Initial fetch
        this.fetchMessages();
        
        // Start polling with exponential backoff on errors
        let retryCount = 0;
        const maxRetryDelay = 30000; // 30 seconds
        
        this.pollInterval = setInterval(() => {
            this.fetchMessages().then(() => {
                // Reset retry count on success
                retryCount = 0;
            }).catch(() => {
                // Exponential backoff on errors
                retryCount++;
                const delay = Math.min(1000 * Math.pow(2, retryCount), maxRetryDelay);
                console.warn(`Polling failed, retrying in ${delay}ms`);
                
                // Restart polling with new delay
                this.stopPolling();
                setTimeout(() => {
                    if (this.currentChatUserId) {
                        this.startPolling();
                    }
                }, delay);
            });
        }, 2000); // Poll every 2 seconds
    }

    stopPolling() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    // Typing indicator functions
    startTyping() {
        if (this.isTyping) return;
        
        this.isTyping = true;
        // In a real app, you would send typing status via WebSocket
        this.showTypingIndicator();
        
        // Clear previous timer
        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
        }
        
        // Stop typing after 3 seconds of inactivity
        this.typingTimer = setTimeout(() => {
            this.stopTyping();
        }, 3000);
    }

    stopTyping() {
        this.isTyping = false;
        this.hideTypingIndicator();
        
        if (this.typingTimer) {
            clearTimeout(this.typingTimer);
            this.typingTimer = null;
        }
    }

    showTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.classList.remove('hidden');
        }
    }

    hideTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.classList.add('hidden');
        }
    }

    // File upload functions
    showUploadProgress() {
        const progress = document.getElementById('upload-progress');
        if (progress) {
            progress.classList.remove('hidden');
            
            // Simulate progress (in real app, you'd use XMLHttpRequest with progress events)
            let progress = 0;
            const interval = setInterval(() => {
                progress += 10;
                this.updateProgressBar(progress);
                
                if (progress >= 90) {
                    clearInterval(interval);
                }
            }, 100);
        }
    }

    hideUploadProgress() {
        const progress = document.getElementById('upload-progress');
        if (progress) {
            progress.classList.add('hidden');
            this.updateProgressBar(0);
        }
    }

    updateProgressBar(percent) {
        const progressBar = document.getElementById('progress-bar');
        const progressPercent = document.getElementById('progress-percent');
        
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
        if (progressPercent) {
            progressPercent.textContent = `${percent}%`;
        }
    }

    // Media modal functions
    openMedia(url, type) {
        const modal = document.getElementById('media-modal');
        const modalImage = document.getElementById('modal-image');
        const modalVideo = document.getElementById('modal-video');
        
        if (type === 'image') {
            modalImage.src = url;
            modalImage.classList.remove('hidden');
            modalVideo.classList.add('hidden');
        } else {
            modalVideo.src = url;
            modalVideo.classList.remove('hidden');
            modalImage.classList.add('hidden');
        }
        
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
    }

    closeMedia() {
        const modal = document.getElementById('media-modal');
        const modalVideo = document.getElementById('modal-video');
        
        modal.classList.add('hidden');
        if (modalVideo) {
            modalVideo.pause();
        }
        document.body.style.overflow = 'auto';
    }

    // Message deletion
    async deleteMessage(messageId) {
        if (!confirm('Apakah Anda yakin ingin menghapus pesan ini?')) {
            return;
        }

        try {
            const response = await fetch('/delete_message/' + messageId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                }
            });
            
            const result = await response.json();
            
            if (result.success) {
                // Remove message from UI
                const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
                if (messageElement) {
                    messageElement.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                    messageElement.style.opacity = '0';
                    messageElement.style.transform = 'translateY(-10px)';
                    
                    setTimeout(() => {
                        messageElement.remove();
                    }, 300);
                }
            } else {
                alert('Gagal menghapus pesan: ' + result.error);
            }
        } catch (error) {
            alert('Error: ' + error);
        }
    }

    // Notification functions
    playNotificationSound() {
        // Simple notification beep using Web Audio API
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.5);
        } catch (e) {
            // Fallback: try using HTML5 audio
            try {
                const audio = new Audio('data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==');
                audio.volume = 0.3;
                audio.play().catch(() => {
                    // Silent fail if audio can't play
                });
            } catch (e2) {
                // Both methods failed, continue silently
            }
        }
    }

    shouldShowDesktopNotification() {
        return (
            'Notification' in window &&
            Notification.permission === 'granted' &&
            document.hidden
        );
    }

    showDesktopNotification(message) {
        if (!this.shouldShowDesktopNotification()) return;
        
        const notification = new Notification('Pesan Baru', {
            body: `${message.sender_username}: ${message.content ? message.content.substring(0, 50) + '...' : 'Mengirim media'}`,
            icon: message.sender_profile_pic,
            tag: 'chat-message'
        });
        
        notification.onclick = function() {
            window.focus();
            this.close();
        };
        
        // Auto-close after 5 seconds
        setTimeout(() => {
            notification.close();
        }, 5000);
    }

    // Connection error handling
    handleConnectionError() {
        // Show connection error indicator
        const chatContainer = document.getElementById('chat-messages');
        if (chatContainer && !document.getElementById('connection-error')) {
            const errorDiv = document.createElement('div');
            errorDiv.id = 'connection-error';
            errorDiv.className = 'bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4 text-center';
            errorDiv.innerHTML = `
                <i class="fas fa-wifi mr-2"></i>
                Koneksi terputus. Mencoba menyambung kembali...
            `;
            chatContainer.appendChild(errorDiv);
        }
        
        // Remove error indicator when connection is restored
        setTimeout(() => {
            const errorDiv = document.getElementById('connection-error');
            if (errorDiv) {
                errorDiv.remove();
            }
        }, 5000);
    }

    // Update unread counts
    async updateUnreadCounts() {
        try {
            // Refresh the dashboard to update unread counts
            const response = await fetch('/');
            const text = await response.text();
            
            // You could parse the HTML and update specific elements
            // For now, we'll update the title if there are unread messages
            this.updatePageTitle();
        } catch (error) {
            console.error('Error updating unread counts:', error);
        }
    }

    updatePageTitle() {
        const unreadElements = document.querySelectorAll('[class*="bg-red-500"]');
        const unreadCount = unreadElements.length;
        
        if (unreadCount > 0) {
            document.title = `(${unreadCount}) Chat App`;
        } else {
            document.title = 'Chat App';
        }
    }

    // Utility functions
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    clearFile() {
        const fileUpload = document.getElementById('file-upload');
        const filePreview = document.getElementById('file-preview');
        
        if (fileUpload) fileUpload.value = '';
        if (filePreview) filePreview.classList.add('hidden');
    }

    // Auto-resize textarea
    autoResize(textarea) {
        textarea.style.height = 'auto';
        textarea.style.height = (textarea.scrollHeight) + 'px';
        
        // Show typing indicator
        if (textarea.value.trim()) {
            this.startTyping();
        } else {
            this.stopTyping();
        }
    }
}

// Initialize global chat manager
const chatManager = new ChatManager();

// Global variables (should be set by the template)
let currentUserId = null;
let currentUserIsAdmin = false;
let csrfToken = '';

// Auto-initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Set global variables from data attributes
    const chatContainer = document.getElementById('chat-messages');
    if (chatContainer) {
        currentUserId = parseInt(chatContainer.dataset.currentUserId || '0');
        currentUserIsAdmin = chatContainer.dataset.currentUserIsAdmin === 'true';
        csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
        
        const targetUserId = document.querySelector('input[name="receiver_id"]')?.value;
        if (targetUserId) {
            chatManager.startChat(parseInt(targetUserId));
        }
    }
    
    // Initialize event listeners
    initializeEventListeners();
});

function initializeEventListeners() {
    // File upload preview
    const fileUpload = document.getElementById('file-upload');
    if (fileUpload) {
        fileUpload.addEventListener('change', function(e) {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                const fileName = document.getElementById('file-name');
                const fileSize = document.getElementById('file-size');
                const filePreview = document.getElementById('file-preview');
                
                if (fileName) fileName.textContent = file.name;
                if (fileSize) fileSize.textContent = chatManager.formatFileSize(file.size);
                if (filePreview) filePreview.classList.remove('hidden');
            }
        });
    }
    
    // Message form submission
    const messageForm = document.getElementById('message-form');
    if (messageForm) {
        messageForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const messageInput = document.getElementById('message-input');
            
            // Validate form
            const content = formData.get('content') || '';
            const file = formData.get('file');
            
            if (!content.trim() && (!file || file.size === 0)) {
                alert('Pesan tidak boleh kosong');
                return;
            }
            
            const result = await chatManager.sendMessage(formData);
            
            if (result.success) {
                // Clear form
                if (messageInput) {
                    messageInput.value = '';
                    messageInput.style.height = 'auto';
                }
                chatManager.clearFile();
                chatManager.stopTyping();
                
                // Add message to UI immediately for better UX
                if (result.message) {
                    chatManager.messageQueue.push(result.message);
                    if (!chatManager.isProcessingQueue) {
                        chatManager.processMessageQueue();
                    }
                }
            } else {
                alert('Gagal mengirim pesan: ' + result.error);
            }
        });
    }
    
    // Message input events
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
        // Auto-resize
        messageInput.addEventListener('input', function() {
            chatManager.autoResize(this);
        });
        
        // Enter key to send (Shift+Enter for new line)
        messageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                messageForm.dispatchEvent(new Event('submit'));
            }
        });
        
        // Stop typing when input loses focus
        messageInput.addEventListener('blur', function() {
            setTimeout(() => chatManager.stopTyping(), 1000);
        });
    }
    
    // Page visibility changes
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            chatManager.stopPolling();
        } else {
            if (chatManager.currentChatUserId) {
                chatManager.startPolling();
            }
        }
    });
    
    // Close modals with Escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            chatManager.closeMedia();
        }
    });
    
    // Handle page unload
    window.addEventListener('beforeunload', function() {
        chatManager.stopPolling();
        chatManager.stopChat();
    });
    
    // Handle online/offline events
    window.addEventListener('online', function() {
        console.log('Connection restored');
        if (chatManager.currentChatUserId) {
            chatManager.startPolling();
        }
    });
    
    window.addEventListener('offline', function() {
        console.log('Connection lost');
        chatManager.stopPolling();
        chatManager.handleConnectionError();
    });
}

// Request notification permission
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission().then(function(permission) {
        console.log('Notification permission:', permission);
    });
}

// Export for global access (if needed)
window.chatManager = chatManager;
window.openMedia = (url, type) => chatManager.openMedia(url, type);
window.closeMedia = () => chatManager.closeMedia();
window.clearFile = () => chatManager.clearFile();