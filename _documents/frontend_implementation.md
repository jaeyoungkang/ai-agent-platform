# 프론트엔드 구현안

## 1. 개요

### 목적
- **LLM과의 대화를 통한 에이전트 생성**
- **코드 작성 최소화로 빠른 구현**
- **단일 화면으로 모든 기능 처리**
- **Claude code cli 터미널을 웹으로 표현한다. 채팅을 치면 클로드 코드와 대화를 하는것**

### 기술 스택 (최소 코드 작성)
- **Framework**: Vanilla JavaScript (프레임워크 없음)
- **Styling**: TailwindCSS CDN (커스텀 CSS 작성 제거)
- **State Management**: 간단한 전역 변수 (localStorage 없이)
- **HTTP Client**: Fetch API


## 2. 단일 페이지 구조

### 2.1 LLM 대화 페이지 (`/index.html`)
**에이전트 생성부터 완료까지 모든 과정을 하나의 페이지에서 처리**

## 3. 완전한 단일 파일 구현

### 3.1 HTML 구조 (index.html - 전체 코드)
```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 에이전트 생성</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 h-screen">
    <div class="max-w-4xl mx-auto h-full flex flex-col p-4">
        <!-- 헤더 -->
        <div class="text-center mb-6">
            <h1 class="text-3xl font-bold text-gray-800">AI 에이전트 생성</h1>
            <p class="text-gray-600 mt-2">LLM과 대화하여 자동화 에이전트를 만들어보세요</p>
        </div>
        
        <!-- 채팅 영역 -->
        <div id="chat" class="flex-1 bg-white rounded-lg shadow-md p-6 mb-4 overflow-y-auto">
            <div id="messages" class="space-y-4">
                <!-- 메시지들이 여기에 추가됨 -->
            </div>
        </div>
        
        <!-- 상태 표시 -->
        <div id="status" class="hidden bg-yellow-100 border border-yellow-400 text-yellow-700 px-4 py-2 rounded mb-4">
            <span id="status-text">처리 중...</span>
        </div>
        
        <!-- 입력 영역 -->
        <div class="bg-white rounded-lg shadow-md p-4">
            <div class="flex gap-2">
                <input 
                    type="text" 
                    id="input" 
                    placeholder="에이전트에 대해 설명해주세요..." 
                    class="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <button 
                    id="send" 
                    class="px-6 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                    전송
                </button>
            </div>
        </div>
    </div>

    <script>
        // 전역 상태 (최소한)
        let messages = [];
        let conversationId = null;
        
        // DOM 요소
        const messagesDiv = document.getElementById('messages');
        const inputField = document.getElementById('input');
        const sendBtn = document.getElementById('send');
        const statusDiv = document.getElementById('status');
        const statusText = document.getElementById('status-text');
        
        // 초기 메시지
        addMessage('assistant', '안녕하세요! 어떤 에이전트를 만들고 싶으신가요?');
        
        // 이벤트 리스너
        sendBtn.onclick = sendMessage;
        inputField.onkeypress = (e) => e.key === 'Enter' && sendMessage();
        
        function addMessage(role, content) {
            const messageDiv = document.createElement('div');
            const isUser = role === 'user';
            
            messageDiv.className = `flex ${isUser ? 'justify-end' : 'justify-start'}`;
            messageDiv.innerHTML = `
                <div class="max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                    isUser 
                        ? 'bg-blue-500 text-white' 
                        : 'bg-gray-200 text-gray-800'
                }">
                    ${content}
                </div>
            `;
            
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        function showStatus(text) {
            statusText.textContent = text;
            statusDiv.classList.remove('hidden');
        }
        
        function hideStatus() {
            statusDiv.classList.add('hidden');
        }
        
        function showComponent(html) {
            const componentDiv = document.createElement('div');
            componentDiv.className = 'mt-4 p-4 bg-blue-50 border border-blue-200 rounded-lg';
            componentDiv.innerHTML = html;
            messagesDiv.appendChild(componentDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
        
        async function sendMessage() {
            const message = inputField.value.trim();
            if (!message) return;
            
            // 사용자 메시지 추가
            addMessage('user', message);
            inputField.value = '';
            
            // 상태 표시
            showStatus('AI가 응답을 생성하고 있습니다...');
            
            try {
                // API 호출
                const response = await fetch('/api/conversation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        conversationId,
                        message
                    })
                });
                
                const data = await response.json();
                
                // 상태 숨기기
                hideStatus();
                
                // 응답 처리
                if (data.text) {
                    addMessage('assistant', data.text);
                }
                
                if (data.status) {
                    showStatus(data.status);
                    setTimeout(hideStatus, 2000);
                }
                
                if (data.component) {
                    showComponent(data.component.html);
                }
                
                if (data.agentCreated) {
                    setTimeout(() => {
                        addMessage('assistant', '✅ 에이전트가 성공적으로 생성되었습니다!');
                    }, 1000);
                }
                
                // conversationId 업데이트
                if (data.conversationId) {
                    conversationId = data.conversationId;
                }
                
            } catch (error) {
                hideStatus();
                addMessage('assistant', '죄송합니다. 오류가 발생했습니다. 다시 시도해주세요.');
                console.error('Error:', error);
            }
        }
    </script>
</body>
</html>
```

## 4. API 연동

### 4.1 필요한 API 엔드포인트
```javascript
// 대화 API (유일한 엔드포인트)
POST /api/conversation
{
    "conversationId": "string|null",
    "message": "string"
}
```

### 4.2 API 응답 형식
```javascript
{
    "conversationId": "새로 생성되거나 기존 ID",
    "text": "AI 응답 텍스트",
    "status": "상태 표시 텍스트 (선택적)",
    "component": {
        "type": "schedule|summary|result", 
        "html": "<div>UI 컴포넌트 HTML</div>"
    },
    "agentCreated": true/false
}
```

## 5. UI 컴포넌트 예시

### 5.1 스케줄 정보 컴포넌트
```html
<div class="bg-green-50 border border-green-200 rounded-lg p-4">
    <h4 class="font-semibold text-green-800 mb-2">✅ 스케줄 설정 완료</h4>
    <div class="text-green-700">
        <p><strong>실행 주기:</strong> 매주</p>
        <p><strong>실행 요일:</strong> 월요일</p>
        <p><strong>실행 시간:</strong> 오전 8:00</p>
    </div>
</div>
```

### 5.2 테스트 결과 컴포넌트
```html
<div class="bg-blue-50 border border-blue-200 rounded-lg p-4">
    <h4 class="font-semibold text-blue-800 mb-2">📊 테스트 결과</h4>
    <div class="text-blue-700">
        <p><strong>총 발견된 뉴스:</strong> 152개</p>
        <p><strong>유효한 뉴스:</strong> 118개</p>
        <p><strong>토큰 사용량:</strong> 입력 1,234 / 출력 2,567</p>
    </div>
</div>
```

## 6. 배포 및 구현

### 6.1 배포 구조 (극단적 단순화)
```
frontend/
└── index.html (완전한 단일 파일)
```

### 6.2 GCP 배포 방법
- **Cloud Run**: API 서버에서 index.html을 정적 파일로 서빙
- **또는 Cloud Storage**: 단일 HTML 파일 호스팅

### 6.3 로컬 개발
```bash
# 단순히 index.html 파일을 브라우저에서 열기
# 또는 간단한 HTTP 서버
python -m http.server 8000
```

## 7. 구현 우선순위 (극단적 단순화)

### 1일 완성 (코드 작성 최소화)
1. **30분**: index.html 파일 생성 (위 코드 복사)
2. **30분**: API 엔드포인트 연결 테스트  
3. **30분**: 상태 표시 및 UI 컴포넌트 테스트
4. **30분**: 전체 통합 테스트 및 배포

## 8. 최대한 코드 작성을 줄인 특징

### ✅ 코드 작성 최소화 방법
- **단일 HTML 파일**: 별도 CSS/JS 파일 없음
- **TailwindCSS CDN**: 커스텀 CSS 작성 제거
- **Vanilla JavaScript**: 프레임워크 학습/설정 시간 제거
- **전역 변수**: 복잡한 상태 관리 없음
- **인라인 함수**: 클래스 구조 없음
- **TailwindCSS 클래스**: 스타일 코드 작성 없음

### ✅ 포함된 핵심 기능
- 채팅 인터페이스
- 상태 표시 (`[상태 표시: 처리 중...]`)
- UI 컴포넌트 표시 (`[UI 컴포넌트: 스케줄 정보]`)
- 에이전트 생성 완료 처리
- API 통신 및 에러 처리

### ❌ 완전히 제외된 기능
- 대시보드 (별도 페이지 없음)
- 에이전트 목록 및 관리
- 복잡한 상태 관리
- 파일 분리
- 커스텀 스타일링
- 테스트 코드

---

**작성일**: 2025-01-18  
**작성자**: Claude Code  
**목표**: 최대한 단순한 구조로 빠른 프론트엔드 구현