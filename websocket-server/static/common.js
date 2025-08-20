/**
 * AI Agent Platform - Common JavaScript Library
 * 공통 UI 컴포넌트 및 유틸리티 함수들
 */

// =============================================================================
// 공통 유틸리티 클래스
// =============================================================================

class Utils {
    /**
     * HTML 문자열 이스케이프
     */
    static escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 시간 포맷팅 (한국어)
     */
    static formatTime(date) {
        return date.toLocaleTimeString('ko-KR', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }

    /**
     * 날짜 포맷팅 (한국어)
     */
    static formatDate(date) {
        return date.toLocaleDateString('ko-KR');
    }

    /**
     * 디바운스 함수
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * 쿠키 설정
     */
    static setCookie(name, value, days) {
        const expires = new Date(Date.now() + days * 864e5).toUTCString();
        document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
    }

    /**
     * 쿠키 읽기
     */
    static getCookie(name) {
        return document.cookie.split('; ').find(row => row.startsWith(name + '='))
            ?.split('=')[1]?.let(decodeURIComponent) || null;
    }

    /**
     * URL 파라미터 파싱
     */
    static getUrlParams() {
        return new URLSearchParams(window.location.search);
    }

    /**
     * 로컬 스토리지 래퍼 (에러 처리 포함)
     */
    static storage = {
        set(key, value) {
            try {
                localStorage.setItem(key, JSON.stringify(value));
            } catch (e) {
                console.warn('LocalStorage write failed:', e);
            }
        },
        
        get(key, defaultValue = null) {
            try {
                const item = localStorage.getItem(key);
                return item ? JSON.parse(item) : defaultValue;
            } catch (e) {
                console.warn('LocalStorage read failed:', e);
                return defaultValue;
            }
        },
        
        remove(key) {
            try {
                localStorage.removeItem(key);
            } catch (e) {
                console.warn('LocalStorage remove failed:', e);
            }
        }
    };
}

// =============================================================================
// 공통 API 클래스
// =============================================================================

class API {
    static baseUrl = '';
    
    /**
     * API 요청 래퍼
     */
    static async request(endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };
        
        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            
            return await response.text();
        } catch (error) {
            console.error(`API request failed: ${endpoint}`, error);
            throw error;
        }
    }

    /**
     * GET 요청
     */
    static async get(endpoint, headers = {}) {
        return this.request(endpoint, { method: 'GET', headers });
    }

    /**
     * POST 요청
     */
    static async post(endpoint, data = {}, headers = {}) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
            headers
        });
    }

    /**
     * PUT 요청
     */
    static async put(endpoint, data = {}, headers = {}) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
            headers
        });
    }

    /**
     * DELETE 요청
     */
    static async delete(endpoint, headers = {}) {
        return this.request(endpoint, { method: 'DELETE', headers });
    }
}

// =============================================================================
// 공통 알림 시스템
// =============================================================================

class Notification {
    static container = null;
    
    static init() {
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'fixed top-4 right-4 z-50 space-y-2';
            document.body.appendChild(this.container);
        }
    }

    static show(message, type = 'info', duration = 5000) {
        this.init();
        
        const notification = document.createElement('div');
        notification.className = this.getNotificationClasses(type);
        
        notification.innerHTML = `
            <div class="flex justify-between items-start">
                <div class="flex items-start space-x-2">
                    <div class="text-lg">${this.getIcon(type)}</div>
                    <span class="text-sm font-medium">${Utils.escapeHtml(message)}</span>
                </div>
                <button onclick="this.parentElement.parentElement.remove()" 
                        class="ml-4 text-gray-400 hover:text-gray-600 text-lg leading-none">
                    ×
                </button>
            </div>
        `;
        
        this.container.appendChild(notification);
        
        // 자동 제거
        if (duration > 0) {
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.remove();
                }
            }, duration);
        }
        
        return notification;
    }

    static getNotificationClasses(type) {
        const baseClasses = 'p-4 rounded-lg shadow-lg max-w-sm border animate-slide-in';
        const typeClasses = {
            success: 'bg-green-50 border-green-200 text-green-800',
            error: 'bg-red-50 border-red-200 text-red-800',
            warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
            info: 'bg-blue-50 border-blue-200 text-blue-800'
        };
        
        return `${baseClasses} ${typeClasses[type] || typeClasses.info}`;
    }

    static getIcon(type) {
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️'
        };
        
        return icons[type] || icons.info;
    }

    static success(message, duration) {
        return this.show(message, 'success', duration);
    }

    static error(message, duration) {
        return this.show(message, 'error', duration);
    }

    static warning(message, duration) {
        return this.show(message, 'warning', duration);
    }

    static info(message, duration) {
        return this.show(message, 'info', duration);
    }

    static clear() {
        if (this.container) {
            this.container.innerHTML = '';
        }
    }
}

// =============================================================================
// 로딩 매니저
// =============================================================================

class LoadingManager {
    static overlay = null;
    static count = 0;

    static init() {
        if (!this.overlay) {
            this.overlay = document.createElement('div');
            this.overlay.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 hidden';
            this.overlay.innerHTML = `
                <div class="bg-white p-6 rounded-lg shadow-xl">
                    <div class="flex items-center space-x-3">
                        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
                        <span class="text-gray-700" id="loading-message">처리 중...</span>
                    </div>
                </div>
            `;
            document.body.appendChild(this.overlay);
        }
    }

    static show(message = '처리 중...') {
        this.init();
        this.count++;
        
        document.getElementById('loading-message').textContent = message;
        this.overlay.classList.remove('hidden');
    }

    static hide() {
        if (this.count > 0) {
            this.count--;
        }
        
        if (this.count === 0 && this.overlay) {
            this.overlay.classList.add('hidden');
        }
    }

    static hideAll() {
        this.count = 0;
        if (this.overlay) {
            this.overlay.classList.add('hidden');
        }
    }
}

// =============================================================================
// 모달 매니저
// =============================================================================

class Modal {
    static modals = new Map();

    static create(id, title, content, options = {}) {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50 hidden';
        modal.id = `modal-${id}`;
        
        modal.innerHTML = `
            <div class="bg-white rounded-lg max-w-md w-full p-6 max-h-full overflow-y-auto">
                <div class="flex justify-between items-center mb-4">
                    <h2 class="text-xl font-bold text-gray-800">${Utils.escapeHtml(title)}</h2>
                    <button onclick="Modal.hide('${id}')" class="text-gray-400 hover:text-gray-600 text-2xl leading-none">×</button>
                </div>
                <div class="modal-content">
                    ${content}
                </div>
                ${options.showButtons !== false ? `
                    <div class="flex justify-end space-x-2 mt-6">
                        <button onclick="Modal.hide('${id}')" class="px-4 py-2 text-gray-600 border border-gray-300 rounded hover:bg-gray-50">
                            ${options.cancelText || '취소'}
                        </button>
                        ${options.confirmCallback ? `
                            <button onclick="${options.confirmCallback}" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">
                                ${options.confirmText || '확인'}
                            </button>
                        ` : ''}
                    </div>
                ` : ''}
            </div>
        `;
        
        document.body.appendChild(modal);
        this.modals.set(id, modal);
        
        // ESC 키로 모달 닫기
        modal.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hide(id);
            }
        });
        
        // 배경 클릭으로 모달 닫기
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                this.hide(id);
            }
        });
        
        return modal;
    }

    static show(id) {
        const modal = this.modals.get(id);
        if (modal) {
            modal.classList.remove('hidden');
            modal.focus();
        }
    }

    static hide(id) {
        const modal = this.modals.get(id);
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    static remove(id) {
        const modal = this.modals.get(id);
        if (modal) {
            modal.remove();
            this.modals.delete(id);
        }
    }

    static confirm(title, message, onConfirm, options = {}) {
        const id = 'confirm-' + Date.now();
        const content = `<p class="text-gray-600">${Utils.escapeHtml(message)}</p>`;
        
        this.create(id, title, content, {
            confirmText: options.confirmText || '확인',
            confirmCallback: `Modal.handleConfirm('${id}', ${onConfirm.name})`,
            ...options
        });
        
        this.show(id);
        
        // 콜백 함수를 글로벌에 등록
        window[`confirmCallback_${id}`] = onConfirm;
    }

    static handleConfirm(id, callbackName) {
        const callback = window[`confirmCallback_${id}`];
        if (callback) {
            callback();
            delete window[`confirmCallback_${id}`];
        }
        this.hide(id);
    }
}

// =============================================================================
// 폼 검증 헬퍼
// =============================================================================

class FormValidator {
    static rules = {
        required: (value) => value?.toString().trim().length > 0,
        email: (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
        minLength: (min) => (value) => value?.toString().length >= min,
        maxLength: (max) => (value) => value?.toString().length <= max,
        pattern: (regex) => (value) => regex.test(value)
    };

    static messages = {
        required: '필수 입력 항목입니다.',
        email: '올바른 이메일 형식이 아닙니다.',
        minLength: (min) => `최소 ${min}자 이상 입력해주세요.`,
        maxLength: (max) => `최대 ${max}자까지 입력 가능합니다.`,
        pattern: '형식이 올바르지 않습니다.'
    };

    static validate(value, rules) {
        for (const rule of rules) {
            if (typeof rule === 'string') {
                if (!this.rules[rule](value)) {
                    return this.messages[rule];
                }
            } else if (typeof rule === 'object') {
                const [ruleName, param] = Object.entries(rule)[0];
                if (!this.rules[ruleName](param)(value)) {
                    return typeof this.messages[ruleName] === 'function' 
                        ? this.messages[ruleName](param)
                        : this.messages[ruleName];
                }
            }
        }
        return null;
    }

    static validateForm(formElement, validationRules) {
        const errors = {};
        let isValid = true;

        for (const [fieldName, rules] of Object.entries(validationRules)) {
            const field = formElement.querySelector(`[name="${fieldName}"]`);
            if (field) {
                const error = this.validate(field.value, rules);
                if (error) {
                    errors[fieldName] = error;
                    isValid = false;
                    this.showFieldError(field, error);
                } else {
                    this.clearFieldError(field);
                }
            }
        }

        return { isValid, errors };
    }

    static showFieldError(field, message) {
        this.clearFieldError(field);
        
        field.classList.add('border-red-500');
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error text-red-500 text-sm mt-1';
        errorDiv.textContent = message;
        
        field.parentNode.appendChild(errorDiv);
    }

    static clearFieldError(field) {
        field.classList.remove('border-red-500');
        
        const existingError = field.parentNode.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }
    }
}

// =============================================================================
// 전역 초기화
// =============================================================================

// 페이지 로드 시 전역 초기화
document.addEventListener('DOMContentLoaded', () => {
    // CSS 애니메이션 추가
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slide-in {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }
        
        .animate-slide-in {
            animation: slide-in 0.3s ease-out;
        }
    `;
    document.head.appendChild(style);
});

// 전역 객체로 노출
window.Utils = Utils;
window.API = API;
window.Notification = Notification;
window.LoadingManager = LoadingManager;
window.Modal = Modal;
window.FormValidator = FormValidator;