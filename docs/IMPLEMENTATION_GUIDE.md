# AI Agent Platform - 구현 가이드 및 기술 참조서

**작성일**: 2025년 8월 22일  
**목적**: 개발자를 위한 시스템 구현 가이드 및 기술적 참조 자료

---

## 🏗️ 시스템 아키텍처

### 전체 구조도
```
┌─────────────────────────────────────────────────────────────┐
│                    사용자 (웹 브라우저)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
┌─────────────────────▼───────────────────────────────────────┐
│              Google Load Balancer                          │
│            (Managed SSL Certificate)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                GKE Autopilot Cluster                       │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │            AI Agent API Server                         │ │
│  │    ┌─────────────┐    ┌─────────────────────────────┐   │ │
│  │    │   FastAPI   │◄──►│      WebSocket Handler      │   │ │
│  │    │   Router    │    │                             │   │ │
│  │    └─────────────┘    └─────────────────────────────┘   │ │
│  │           │                        │                   │ │
│  │           ▼                        ▼                   │ │
│  │ ┌─────────────────┐    ┌─────────────────────────────┐ │ │
│  │ │ Google OAuth2   │    │    User Workspace           │ │ │
│  │ │ Authentication  │    │    Management               │ │ │
│  │ └─────────────────┘    └─────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Google Cloud Services                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Firestore  │  │Secret Manager│  │  Gmail SMTP        │  │
│  │  Database   │  │   API Keys   │  │  Email Service     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 🔧 Google OAuth 2.0 구현

### 완전 구현된 OAuth 플로우

#### 1. 클라이언트 사이드 (JavaScript)
```javascript
// Google Identity Services API 사용 (최신 방식)
function initializeGoogleAuth() {
    google.accounts.id.initialize({
        client_id: "711734862853-acs8f4a8vl5nm6qmj7nncgf8fhf0dpmf.apps.googleusercontent.com",
        callback: handleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: false
    });
    
    google.accounts.id.renderButton(
        document.getElementById("google-signin"),
        { 
            theme: "outline", 
            size: "large",
            width: 250
        }
    );
}

async function handleCredentialResponse(response) {
    const token = response.credential;
    
    // 서버로 JWT 토큰 전송
    const authResponse = await fetch('/api/auth/google', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: token })
    });
    
    if (authResponse.ok) {
        const userData = await authResponse.json();
        // 로그인 성공 처리
        localStorage.setItem('user', JSON.stringify(userData));
        window.location.href = '/assets/dashboard.html';
    }
}
```

#### 2. 서버 사이드 (FastAPI)
```python
from google.oauth2 import id_token
from google.auth.transport import requests
import json

GOOGLE_CLIENT_ID = "711734862853-acs8f4a8vl5nm6qmj7nncgf8fhf0dpmf.apps.googleusercontent.com"

@app.post("/api/auth/google")
async def google_auth(request: GoogleAuthRequest):
    try:
        # Google JWT 토큰 검증
        idinfo = id_token.verify_oauth2_token(
            request.token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        
        # 토큰 유효성 확인
        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError('잘못된 issuer')
        
        # 사용자 정보 추출
        user_data = {
            "google_id": idinfo['sub'],
            "email": idinfo['email'],
            "name": idinfo['name'],
            "picture": idinfo.get('picture', ''),
            "verified_email": idinfo['email_verified']
        }
        
        # Firestore에 사용자 정보 저장/업데이트
        await store_or_update_user(user_data)
        
        return {"success": True, "user": user_data}
        
    except ValueError as e:
        logger.error(f"Google Auth Error: {e}")
        raise HTTPException(status_code=401, detail="인증 실패")
```

## 📧 이메일 서비스 구현

### Gmail SMTP 설정 (현재 구현)
```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

class EmailService:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.username = os.getenv('SMTP_USERNAME')  # noreply@send.app
        self.password = os.getenv('SMTP_PASSWORD')  # 앱 비밀번호
        
    async def send_beta_application_email(self, user_data: dict):
        """베타 신청 접수 확인 이메일 발송"""
        subject = "[AI Agent Platform] 베타 신청이 접수되었습니다"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>베타 신청 접수 확인</title>
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px;">
                <h2 style="color: #2c3e50;">안녕하세요, {user_data['name']}님!</h2>
                
                <p>AI Agent Platform 베타 서비스에 신청해 주셔서 감사합니다.</p>
                
                <div style="background-color: white; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3>신청 정보</h3>
                    <ul>
                        <li><strong>이름:</strong> {user_data['name']}</li>
                        <li><strong>이메일:</strong> {user_data['email']}</li>
                        <li><strong>신청일시:</strong> {user_data['applied_at']}</li>
                    </ul>
                </div>
                
                <p>베타 서비스 승인은 순차적으로 진행되며, 승인 완료시 별도로 안내드리겠습니다.</p>
                
                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 12px;">
                    이 메일은 자동으로 발송되었습니다.<br>
                    문의사항이 있으시면 j@youngcompany.kr로 연락해 주세요.
                </p>
            </div>
        </body>
        </html>
        """
        
        await self._send_email(user_data['email'], subject, html_content)
    
    async def _send_email(self, to_email: str, subject: str, html_content: str):
        """실제 이메일 발송 처리"""
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.username
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(html_part)
        
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            logger.info(f"Email sent successfully to {to_email}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise
```

## 🔄 CI/CD 파이프라인 구현

### GitHub Actions 워크플로우
```yaml
name: Deploy to GKE Autopilot

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

env:
  PROJECT_ID: ai-agent-platform-469401
  GKE_CLUSTER: ai-agent-cluster
  GKE_ZONE: asia-northeast3
  DEPLOYMENT_NAME: ai-agent-api
  IMAGE: api-server

jobs:
  setup-build-publish-deploy:
    name: Setup, Build, Publish, and Deploy
    runs-on: ubuntu-latest
    
    permissions:
      contents: read
      id-token: write

    steps:
    - name: Checkout
      uses: actions/checkout@v3

    - id: 'auth'
      name: 'Authenticate to Google Cloud'
      uses: 'google-github-actions/auth@v1'
      with:
        workload_identity_provider: 'projects/711734862853/locations/global/workloadIdentityPools/github-pool/providers/github-provider'
        service_account: 'github-actions-sa@ai-agent-platform-469401.iam.gserviceaccount.com'

    - name: 'Set up Cloud SDK'
      uses: 'google-github-actions/setup-gcloud@v1'

    - name: 'Configure Docker to use gcloud as a credential helper'
      run: |-
        gcloud auth configure-docker gcr.io

    - name: Build Docker image
      run: |-
        cd websocket-server
        docker build --platform linux/amd64 \
          --tag "gcr.io/$PROJECT_ID/$IMAGE:$GITHUB_SHA" \
          --tag "gcr.io/$PROJECT_ID/$IMAGE:latest" .

    - name: Push Docker image
      run: |-
        docker push "gcr.io/$PROJECT_ID/$IMAGE:$GITHUB_SHA"
        docker push "gcr.io/$PROJECT_ID/$IMAGE:latest"

    - name: Get GKE credentials
      run: |-
        gcloud container clusters get-credentials "$GKE_CLUSTER" --zone "$GKE_ZONE"

    - name: Deploy to GKE
      run: |-
        kubectl set image deployment/$DEPLOYMENT_NAME api-server=gcr.io/$PROJECT_ID/$IMAGE:$GITHUB_SHA
        kubectl rollout status deployment/$DEPLOYMENT_NAME
        kubectl get services -o wide
```

## 🌐 웹 라우팅 구조

### FastAPI 라우팅 설정
```python
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI(title="AI Agent Platform API")

# 정적 파일 서빙 (CSS, JS 등은 /assets/ 경로로)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")

@app.get("/")
async def root():
    """루트 경로에서 메인 페이지 직접 서빙"""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        return {"message": "AI Agent Platform", "error": "index.html not found"}

# API 라우터
@app.get("/api/agents")
async def get_agents():
    """에이전트 목록 조회"""
    # Firestore에서 에이전트 목록 가져오기
    pass

@app.post("/api/agents")
async def create_agent(agent_data: AgentCreateRequest):
    """새 에이전트 생성"""
    # Firestore에 새 에이전트 저장
    pass

# WebSocket 연결
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """실시간 채팅을 위한 WebSocket 연결"""
    await websocket.accept()
    
    # 사용자 세션 관리 및 메시지 처리
    user_workspace = UserWorkspace(session_id)
    
    try:
        while True:
            # 클라이언트로부터 메시지 수신
            message = await websocket.receive_text()
            
            # Claude Code 시뮬레이션 응답 생성
            response = await user_workspace.send_to_claude(message)
            
            # 응답을 클라이언트로 전송
            await websocket.send_text(response)
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    finally:
        await user_workspace.cleanup()
```

## 🗄️ Firestore 데이터베이스 구조

### 컬렉션 스키마
```javascript
// users 컬렉션
{
  "google_id": "string",           // Google OAuth ID
  "email": "string",               // 사용자 이메일
  "name": "string",                // 사용자 이름
  "picture": "string",             // 프로필 이미지 URL
  "verified_email": "boolean",     // 이메일 인증 여부
  "created_at": "timestamp",       // 가입일시
  "last_login": "timestamp",       // 마지막 로그인
  "beta_approved": "boolean"       // 베타 승인 여부
}

// agents 컬렉션
{
  "name": "string",                // 에이전트 이름
  "description": "string",         // 에이전트 설명
  "owner_id": "string",           // 소유자 Google ID
  "created_at": "timestamp",       // 생성일시
  "updated_at": "timestamp",       // 수정일시
  "config": {                      // 에이전트 설정
    "model": "string",
    "temperature": "number",
    "max_tokens": "number"
  }
}

// sessions 컬렉션
{
  "session_id": "string",          // 세션 ID
  "user_id": "string",            // 사용자 Google ID
  "agent_id": "string",           // 연결된 에이전트 ID
  "created_at": "timestamp",       // 세션 시작시간
  "last_activity": "timestamp",    // 마지막 활동시간
  "status": "string"              // active, inactive, closed
}
```

## 🔒 보안 설정

### Kubernetes 보안 구성
```yaml
# k8s/security/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ai-agent-api-netpol
spec:
  podSelector:
    matchLabels:
      app: ai-agent-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: gke-system
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to: []
    ports:
    - protocol: TCP
      port: 443  # HTTPS 외부 API 호출
    - protocol: TCP
      port: 587  # SMTP
    - protocol: TCP
      port: 53   # DNS
    - protocol: UDP
      port: 53   # DNS
```

### Secret Management
```yaml
# k8s/secrets/app-secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
stringData:
  GOOGLE_CLIENT_ID: "711734862853-acs8f4a8vl5nm6qmj7nncgf8fhf0dpmf.apps.googleusercontent.com"
  SMTP_USERNAME: "noreply@send.app"
  SMTP_PASSWORD: "${GMAIL_APP_PASSWORD}"
  FIRESTORE_CREDENTIALS: "${FIRESTORE_SERVICE_ACCOUNT_JSON}"
```

## 🧪 테스트 및 모니터링

### 기능 테스트 스크립트
```bash
#!/bin/bash
# test-endpoints.sh

BASE_URL="https://oh-my-agent.info"

echo "=== API Endpoint Tests ==="

# Health check
echo "Testing health endpoint..."
curl -f "${BASE_URL}/api/health" || echo "❌ Health check failed"

# Static assets
echo "Testing static assets..."
curl -f "${BASE_URL}/assets/styles.css" > /dev/null && echo "✅ CSS loading OK" || echo "❌ CSS failed"
curl -f "${BASE_URL}/assets/common.js" > /dev/null && echo "✅ JS loading OK" || echo "❌ JS failed"

# Main page
echo "Testing main page..."
curl -f "${BASE_URL}/" > /dev/null && echo "✅ Main page OK" || echo "❌ Main page failed"

echo "=== All tests completed ==="
```

---

## 📋 개발자 참고사항

### 로컬 개발 환경 설정
```bash
# 1. 환경 변수 설정
export CLOUDBUILD_MOCK=true
export PORT=8001
export GOOGLE_CLIENT_ID="your-client-id"
export SMTP_USERNAME="j@yyoungcompany.kr"
export SMTP_PASSWORD="your-app-password"

# 2. 의존성 설치
cd websocket-server
pip install -r requirements.txt

# 3. 로컬 서버 실행
python main.py

# 4. 브라우저에서 접속
open http://localhost:8000
```

### 디버깅 팁
1. **OAuth 문제**: 개발자 도구 콘솔에서 JavaScript 오류 확인
2. **WebSocket 연결**: 네트워크 탭에서 WS 연결 상태 모니터링
3. **이메일 발송**: 서버 로그에서 SMTP 연결 상태 확인
4. **Firestore**: GCP 콘솔에서 데이터베이스 쿼리 직접 실행

### 확장 가이드
1. **새 API 엔드포인트 추가**: FastAPI 라우터 패턴 사용
2. **데이터베이스 스키마 변경**: Firestore 컬렉션 구조 업데이트
3. **인증 확장**: 추가 OAuth 제공자 연동 가능

이 가이드는 현재 운영 중인 시스템의 실제 구현사항을 바탕으로 작성되었습니다.