/**
 * AI Agent Platform - Onboarding JavaScript
 * 베타 사용자 온보딩 플로우 관리
 */

class OnboardingManager {
    constructor() {
        this.currentStep = 'interests';
        this.userInterests = [];
        this.nickname = '';
        this.userId = null;
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadUserInfo();
        this.updateProgressBar();
    }
    
    setupEventListeners() {
        // 관심사 체크박스 이벤트
        document.querySelectorAll('input[name="interests"]').forEach(checkbox => {
            checkbox.addEventListener('change', this.handleInterestChange.bind(this));
        });
        
        // 닉네임 입력 이벤트
        const nicknameInput = document.getElementById('nickname');
        nicknameInput.addEventListener('input', this.handleNicknameChange.bind(this));
        nicknameInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !document.getElementById('complete-interests').disabled) {
                this.completeOnboarding();
            }
        });
        
        // 완료 버튼 이벤트
        document.getElementById('complete-interests').addEventListener('click',
            this.completeOnboarding.bind(this));
            
        // 액션 버튼 이벤트
        document.getElementById('start-tour').addEventListener('click',
            this.startTour.bind(this));
        document.getElementById('create-direct').addEventListener('click',
            this.createDirect.bind(this));
        document.getElementById('skip-tour').addEventListener('click',
            this.skipTour.bind(this));
    }
    
    async loadUserInfo() {
        try {
            // URL에서 사용자 정보 확인 (개발 단계에서는 임시)
            const urlParams = new URLSearchParams(window.location.search);
            const tempUserId = urlParams.get('user_id');
            
            if (tempUserId) {
                this.userId = tempUserId;
            } else {
                // 게스트 세션 생성
                try {
                    const authData = await API.post('/api/auth/guest', {});
                    if (authData && authData.user_id) {
                        this.userId = authData.user_id;
                        console.log('Created guest session:', this.userId);
                    } else {
                        throw new Error('Failed to create guest session');
                    }
                } catch (error) {
                    console.error('Guest auth failed:', error);
                    // 폴백: 임시 사용자 ID 생성
                    this.userId = 'guest-user-' + Date.now();
                }
            }
            
            // 사용자 프로필 로드 시도
            const userProfile = await this.fetchUserProfile();
            if (userProfile && userProfile.onboarding_completed) {
                // 이미 온보딩 완료한 사용자는 대시보드로 이동
                window.location.href = '/assets/dashboard.html';
            }
            
        } catch (error) {
            console.error('Failed to load user info:', error);
            // 에러가 발생해도 온보딩 진행
        }
    }
    
    async fetchUserProfile() {
        try {
            return await API.get('/api/user/profile', {
                'X-User-Id': this.userId
            });
        } catch (error) {
            console.error('Error fetching user profile:', error);
            return null;
        }
    }
    
    handleInterestChange(event) {
        const value = event.target.value;
        const card = event.target.closest('.interest-card');
        
        if (event.target.checked) {
            this.userInterests.push(value);
            card.classList.add('selected');
        } else {
            this.userInterests = this.userInterests.filter(i => i !== value);
            card.classList.remove('selected');
        }
        
        this.updateCompleteButton();
    }
    
    handleNicknameChange(event) {
        this.nickname = event.target.value.trim();
        this.updateCompleteButton();
    }
    
    updateCompleteButton() {
        const button = document.getElementById('complete-interests');
        const isValid = this.userInterests.length > 0 && this.nickname.length >= 2;
        
        button.disabled = !isValid;
        
        if (isValid) {
            button.classList.remove('opacity-50', 'cursor-not-allowed');
        } else {
            button.classList.add('opacity-50', 'cursor-not-allowed');
        }
    }
    
    async completeOnboarding() {
        if (this.userInterests.length === 0 || this.nickname.length < 2) {
            Notification.warning('관심사를 최소 1개 선택하고, 닉네임을 2글자 이상 입력해주세요.');
            return;
        }
        
        LoadingManager.show('온보딩 정보를 저장하는 중...');
        
        try {
            const result = await API.post('/api/user/onboarding', {
                interests: this.userInterests,
                nickname: this.nickname
            }, {
                'X-User-Id': this.userId
            });
            
            console.log('Onboarding completed:', result);
            
            // 완료 단계로 이동
            this.showStep('step-complete');
            document.getElementById('user-nickname').textContent = this.nickname;
            this.currentStep = 'complete';
            this.updateProgressBar();
            
            // 성공 메시지 표시
            Notification.success(`환영합니다, ${this.nickname}님! 온보딩이 완료되었습니다.`);
            
        } catch (error) {
            console.error('Failed to complete onboarding:', error);
            Notification.error('온보딩 완료 중 오류가 발생했습니다. 다시 시도해주세요.');
        } finally {
            LoadingManager.hide();
        }
    }
    
    showStep(stepId) {
        // 모든 단계 숨기기
        document.querySelectorAll('#step-interests, #step-complete').forEach(step => {
            step.classList.add('hidden');
        });
        
        // 현재 단계 보이기
        document.getElementById(stepId).classList.remove('hidden');
    }
    
    updateProgressBar() {
        const steps = {
            'interests': 2,
            'complete': 3
        };
        
        const currentStepNum = steps[this.currentStep] || 2;
        
        document.querySelectorAll('.progress-step').forEach((step, index) => {
            const stepNum = index + 1;
            
            if (stepNum < currentStepNum) {
                step.className = 'progress-step completed';
            } else if (stepNum === currentStepNum) {
                step.className = 'progress-step active';
            } else {
                step.className = 'progress-step pending';
            }
        });
    }
    
    // showLoading과 showAlert 메서드는 공통 라이브러리로 대체됨
    
    startTour() {
        // 가이드 투어 모드로 대시보드 이동
        Notification.success('가이드 투어를 시작합니다!');
        setTimeout(() => {
            window.location.href = '/assets/dashboard.html?tour=true';
        }, 1500);
    }
    
    createDirect() {
        // 바로 에이전트 생성 모드로 이동
        Notification.success('첫 번째 에이전트 생성을 시작합니다!');
        setTimeout(() => {
            window.location.href = '/assets/dashboard.html?create=true';
        }, 1500);
    }
    
    skipTour() {
        // 일반 대시보드로 이동
        Notification.info('대시보드로 이동합니다!');
        setTimeout(() => {
            window.location.href = '/static/dashboard.html';
        }, 1500);
    }
    
    // 선택된 관심사 표시를 위한 스타일 업데이트
    updateInterestCardStyles() {
        document.querySelectorAll('input[name="interests"]').forEach(checkbox => {
            const card = checkbox.closest('.interest-card');
            if (checkbox.checked) {
                card.classList.add('ring-2', 'ring-blue-500', 'bg-blue-50');
                card.querySelector('.interest-icon').classList.add('bg-blue-500', 'text-white');
            } else {
                card.classList.remove('ring-2', 'ring-blue-500', 'bg-blue-50');
                card.querySelector('.interest-icon').classList.remove('bg-blue-500', 'text-white');
            }
        });
    }
}

// 유틸리티 함수들
class OnboardingUtils {
    static validateNickname(nickname) {
        if (!nickname || nickname.trim().length < 2) {
            return { valid: false, message: '닉네임은 2글자 이상이어야 합니다.' };
        }
        
        if (nickname.length > 20) {
            return { valid: false, message: '닉네임은 20글자를 초과할 수 없습니다.' };
        }
        
        // 특수문자 제한 (기본적인 한글, 영문, 숫자, 스페이스만 허용)
        const validPattern = /^[가-힣a-zA-Z0-9\s]+$/;
        if (!validPattern.test(nickname)) {
            return { valid: false, message: '닉네임은 한글, 영문, 숫자, 공백만 사용 가능합니다.' };
        }
        
        return { valid: true, message: '' };
    }
    
    static getInterestDisplayName(interestKey) {
        const interestMap = {
            'investment': '투자/재정 관리',
            'news': '뉴스/정보 수집',
            'analytics': '데이터 분석/리포트',
            'communication': '커뮤니케이션',
            'ecommerce': '전자상거래',
            'research': '학습/연구',
            'business': '업무 자동화',
            'personal': '개인 생활',
            'marketing': '마케팅/영업'
        };
        
        return interestMap[interestKey] || interestKey;
    }
}

// DOM 로드 완료 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    // 전역 온보딩 관리자 생성
    window.onboardingManager = new OnboardingManager();
    
    // 개발 환경에서 디버그 정보 출력
    if (window.location.hostname === 'localhost') {
        console.log('Onboarding Manager initialized');
        console.log('Current environment: development');
    }
});

// 전역 함수로 노출 (HTML에서 직접 호출 가능)
window.OnboardingUtils = OnboardingUtils;