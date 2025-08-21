#!/usr/bin/env python3
"""
AI Agent Platform - Kubernetes-Native API Server
Kubernetes Pod에서 직접 실행되는 클라우드 네이티브 아키텍처
"""

import asyncio
import json
import uuid
import logging
import os
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# .env.local 파일 로드
load_dotenv(dotenv_path="../.env.local")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import List, Optional
import google.cloud.firestore as firestore
from auth import auth_manager, google_auth, beta_manager
from email_service import email_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firestore
db = firestore.Client()

class UserWorkspace:
    """사용자별 세션 관리 (Kubernetes-Native)"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session_data = {}
        
    async def send_to_claude(self, message: str, agent_id: str = None) -> str:
        """메시지 처리 및 시뮬레이션 응답 생성"""
        logger.info(f"Processing message for user {self.user_id} (agent: {agent_id or 'none'})")
        
        # Kubernetes 환경에서 Claude Code CLI 시뮬레이션
        response = f"""Claude Code CLI 시뮬레이션 응답

사용자 메시지: {message}

현재 Kubernetes Pod 환경에서 실행 중입니다.
- 환경: GKE Autopilot
- Pod 리소스: 1-2GB RAM, 0.5-1 CPU
- 데이터 저장: Firestore
- 보안: Workload Identity

실제 Claude Code CLI 기능을 사용하려면 다음 중 하나를 구현하세요:
1. Cloud Run Jobs를 이용한 별도 워크스페이스 서비스
2. GKE에서 Docker-in-Docker 지원하는 전용 노드풀
3. 외부 워크스페이스 서비스 연동

현재는 에이전트 생성/관리 기능이 완전히 작동합니다."""

        return response
    
    async def cleanup(self):
        """세션 정리"""
        logger.info(f"Cleaned up session for user {self.user_id}")
        self.session_data.clear()

class ConnectionManager:
    """WebSocket 연결 관리"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_workspaces: Dict[str, UserWorkspace] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_workspaces[user_id] = UserWorkspace(user_id)
        logger.info(f"User {user_id} connected")
    
    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_workspaces:
            # 세션 정리는 별도 태스크로 처리
            asyncio.create_task(self.user_workspaces[user_id].cleanup())
            del self.user_workspaces[user_id]
        logger.info(f"User {user_id} disconnected")
    
    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)
    
    async def process_user_message(self, user_id: str, message: str, agent_id: str = None) -> str:
        """사용자 메시지를 Claude로 전달하고 응답 받기"""
        if user_id not in self.user_workspaces:
            return "Error: Workspace not found"
        
        workspace = self.user_workspaces[user_id]
        response = await workspace.send_to_claude(message, agent_id)
        
        # Firestore에 대화 기록 저장
        await self._save_conversation(user_id, message, response, agent_id)
        
        return response
    
    async def _save_conversation(self, user_id: str, user_message: str, assistant_response: str, agent_id: str = None):
        """Firestore에 대화 기록 저장"""
        try:
            conversation_ref = db.collection('conversations').document()
            conversation_data = {
                'userId': user_id,
                'agentId': agent_id,
                'messages': [
                    {
                        'role': 'user',
                        'content': user_message,
                        'timestamp': datetime.utcnow()
                    },
                    {
                        'role': 'assistant',
                        'content': assistant_response,
                        'timestamp': datetime.utcnow()
                    }
                ],
                'createdAt': datetime.utcnow()
            }
            conversation_ref.set(conversation_data)
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")

# FastAPI 애플리케이션 초기화
app = FastAPI(title="AI Agent Platform", version="1.1.0")

# 요청 검증 오류 핸들러
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 검증 오류 상세 처리"""
    logger.error(f"Validation error for {request.url}: {exc.errors()}")
    
    # body를 안전하게 문자열로 변환
    body_str = None
    if hasattr(exc, 'body') and exc.body:
        try:
            if isinstance(exc.body, bytes):
                body_str = exc.body.decode('utf-8')
            else:
                body_str = str(exc.body)
        except:
            body_str = "Unable to decode body"
    
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": body_str}
    )

# 보안 미들웨어 설정
# 신뢰할 수 있는 호스트만 허용 (헬스체크 IP 포함)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["oh-my-agent.info", "app.oh-my-agent.info", "localhost", "127.0.0.1", "*"]
)

# CORS 설정 (HTTPS 전환 후 더 엄격하게)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://oh-my-agent.info", "https://app.oh-my-agent.info", "http://localhost:*", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 보안 헤더 미들웨어
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # 보안 헤더 추가
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # HTTPS에서만 HSTS 헤더 적용
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    # Content Security Policy
    csp_policy = (
        "default-src 'self'; "
        "connect-src 'self' https://www.googleapis.com https://accounts.google.com wss://oh-my-agent.info wss://app.oh-my-agent.info; "
        "script-src 'self' https://accounts.google.com 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    response.headers["Content-Security-Policy"] = csp_policy
    
    return response

# 연결 매니저 초기화
manager = ConnectionManager()

@app.websocket("/workspace/{user_id}")
async def user_workspace(websocket: WebSocket, user_id: str):
    """사용자 전용 워크스페이스 - Kubernetes Pod 세션 기반"""
    await manager.connect(websocket, user_id)
    
    try:
        # 환영 메시지 전송
        welcome_message = {
            "type": "system",
            "content": f"Kubernetes Pod 워크스페이스에 연결되었습니다. AI 에이전트와 대화를 시작하세요.",
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_text(json.dumps(welcome_message))
        
        # 메시지 처리 루프
        while True:
            # 사용자 메시지 수신
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get('message', '')
            
            if user_message:
                # AI 에이전트로 메시지 전달
                agent_response = await manager.process_user_message(user_id, user_message)
                
                # 응답 전송
                response_data = {
                    "type": "agent_response",
                    "content": agent_response,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send_text(json.dumps(response_data))
                
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(user_id)

@app.get("/health")
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.3", "registry": "artifact-registry"}

@app.post("/api/auth/guest")
async def create_guest_session(request: Request):
    """게스트 세션 생성"""
    user_agent = request.headers.get("user-agent", "")
    session_data = await auth_manager.create_guest_session(user_agent)
    return JSONResponse(content=session_data)

@app.get("/api/auth/validate/{session_id}")
async def validate_session(session_id: str):
    """세션 유효성 검사"""
    session = await auth_manager.validate_session(session_id)
    if session:
        return JSONResponse(content={
            "valid": True,
            "user_id": session["user_id"],
            "user_type": session["user_type"]
        })
    else:
        return JSONResponse(content={"valid": False}, status_code=401)

# 베타 사용자 관리 API
@app.get("/api/beta/count")
async def get_beta_count():
    """베타 사용자 수 조회"""
    try:
        count = await beta_manager.get_beta_user_count()
        return {"count": count, "max": 30, "remaining": 30 - count}
    except Exception as e:
        logger.error(f"Error getting beta count: {e}")
        return {"count": 17, "max": 30, "remaining": 13}  # 기본값

# 베타 신청 데이터 모델
class BetaApplicationRequest(BaseModel):
    email: str
    name: str
    company: Optional[str] = ""
    use_case: str
    experience: str
    agree_terms: bool

@app.post("/api/beta/apply")
async def apply_beta(request: Request):
    """베타 참여 신청"""
    try:
        # 원시 요청 데이터 로깅
        body = await request.body()
        logger.info(f"Beta application raw body: {body.decode('utf-8') if body else 'Empty'}")
        
        # JSON 파싱
        try:
            request_data = await request.json()
            logger.info(f"Beta application parsed data: {request_data}")
        except Exception as parse_error:
            logger.error(f"Beta application JSON parsing error: {parse_error}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Pydantic 모델 검증
        try:
            application_data = BetaApplicationRequest(**request_data)
        except Exception as validation_error:
            logger.error(f"Beta application validation error: {validation_error}")
            raise HTTPException(status_code=422, detail=str(validation_error))
        
        # 이미 신청한 이메일인지 확인
        existing_applications = db.collection('beta_applications').where('email', '==', application_data.email).stream()
        if len(list(existing_applications)) > 0:
            raise HTTPException(status_code=409, detail="이미 신청하신 이메일입니다.")
        
        # 베타 신청 데이터 저장
        application_ref = db.collection('beta_applications').document()
        applied_at = datetime.utcnow()
        
        application_doc = {
            'email': application_data.email,
            'name': application_data.name,
            'company': application_data.company,
            'use_case': application_data.use_case,
            'experience': application_data.experience,
            'status': 'pending',
            'applied_at': applied_at,
            'approved_at': None,
            'approved_by': None,
            'notes': ''
        }
        
        application_ref.set(application_doc)
        
        # 이메일 발송 (비동기)
        user_data = {
            'name': application_data.name,
            'email': application_data.email,
            'company': application_data.company,
            'use_case': application_data.use_case,
            'experience': application_data.experience,
            'applied_at': applied_at.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # 관리자 알림 이메일 발송
        admin_email_success = await email_service.send_beta_application_notification(user_data)
        
        # 신청자 접수 확인 이메일 발송
        confirmation_email_success = await email_service.send_application_confirmation(
            application_data.email, 
            application_data.name,
            applied_at.strftime('%Y-%m-%d %H:%M:%S')
        )
        
        logger.info(f"Beta application submitted: {application_data.email}")
        logger.info(f"Admin notification email: {'sent' if admin_email_success else 'failed'}")
        logger.info(f"Confirmation email: {'sent' if confirmation_email_success else 'failed'}")
        
        return {
            "success": True,
            "message": "베타 신청이 완료되었습니다. 이메일을 확인해주세요.",
            "application_id": application_ref.id,
            "email_status": {
                "admin_notification": admin_email_success,
                "user_confirmation": confirmation_email_success
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing beta application: {e}")
        raise HTTPException(status_code=500, detail="베타 신청 처리 중 오류가 발생했습니다.")

# 화이트리스트 관리 함수
async def check_whitelist(email: str) -> bool:
    """화이트리스트 확인"""
    try:
        whitelist_ref = db.collection('whitelist').where('email', '==', email).where('status', '==', 'active')
        docs = list(whitelist_ref.stream())
        return len(docs) > 0
    except Exception as e:
        logger.error(f"Error checking whitelist for {email}: {e}")
        return False

async def add_to_whitelist(email: str, name: str, admin_email: str = "admin", notes: str = "") -> bool:
    """화이트리스트 추가"""
    try:
        whitelist_ref = db.collection('whitelist').document()
        whitelist_data = {
            'email': email,
            'name': name,
            'added_at': datetime.utcnow(),
            'added_by': admin_email,
            'status': 'active',
            'notes': notes
        }
        whitelist_ref.set(whitelist_data)
        
        # 승인 이메일 발송
        await email_service.send_approval_notification(email, name)
        
        logger.info(f"Added {email} to whitelist by {admin_email}")
        return True
    except Exception as e:
        logger.error(f"Error adding {email} to whitelist: {e}")
        return False

# 화이트리스트 관리 API
class WhitelistAddRequest(BaseModel):
    email: str
    name: str
    notes: Optional[str] = ""

@app.post("/api/admin/whitelist/add")
async def add_whitelist(request: WhitelistAddRequest):
    """화이트리스트에 이메일 추가"""
    try:
        # 이미 화이트리스트에 있는지 확인
        if await check_whitelist(request.email):
            raise HTTPException(status_code=409, detail="이미 화이트리스트에 등록된 이메일입니다.")
        
        success = await add_to_whitelist(request.email, request.name, "admin", request.notes)
        
        if success:
            return {"success": True, "message": f"{request.email}이 화이트리스트에 추가되었습니다."}
        else:
            raise HTTPException(status_code=500, detail="화이트리스트 추가에 실패했습니다.")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in add_whitelist API: {e}")
        raise HTTPException(status_code=500, detail="화이트리스트 추가 중 오류가 발생했습니다.")

@app.get("/api/admin/whitelist")
async def get_whitelist():
    """화이트리스트 조회"""
    try:
        whitelist_ref = db.collection('whitelist').order_by('added_at', direction=firestore.Query.DESCENDING)
        whitelist = []
        
        for doc in whitelist_ref.stream():
            whitelist_data = doc.to_dict()
            whitelist_data['id'] = doc.id
            whitelist.append(whitelist_data)
        
        return {"whitelist": whitelist, "count": len(whitelist)}
        
    except Exception as e:
        logger.error(f"Error fetching whitelist: {e}")
        raise HTTPException(status_code=500, detail="화이트리스트 조회에 실패했습니다.")

@app.delete("/api/admin/whitelist/{email}")
async def remove_whitelist(email: str):
    """화이트리스트에서 이메일 제거"""
    try:
        # 해당 이메일의 화이트리스트 문서 찾기
        whitelist_ref = db.collection('whitelist').where('email', '==', email)
        docs = list(whitelist_ref.stream())
        
        if len(docs) == 0:
            raise HTTPException(status_code=404, detail="화이트리스트에서 찾을 수 없는 이메일입니다.")
        
        # 모든 매칭되는 문서 삭제 (중복 방지)
        for doc in docs:
            doc.reference.delete()
        
        logger.info(f"Removed {email} from whitelist")
        return {"success": True, "message": f"{email}이 화이트리스트에서 제거되었습니다."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing {email} from whitelist: {e}")
        raise HTTPException(status_code=500, detail="화이트리스트 제거에 실패했습니다.")

# Google OAuth 인증 모델
class GoogleAuthRequest(BaseModel):
    google_token: str
    user_info: dict

@app.post("/api/auth/google")
async def google_auth(request: Request):
    """Google OAuth 인증"""
    try:
        # 원시 요청 데이터 로깅
        body = await request.body()
        logger.info(f"Raw request body: {body.decode('utf-8') if body else 'Empty'}")
        
        # JSON 파싱 시도
        try:
            request_data = await request.json()
            logger.info(f"Parsed JSON keys: {list(request_data.keys()) if isinstance(request_data, dict) else 'Not a dict'}")
        except Exception as parse_error:
            logger.error(f"JSON parsing error: {parse_error}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Pydantic 모델 검증
        try:
            auth_request = GoogleAuthRequest(**request_data)
        except Exception as validation_error:
            logger.error(f"Pydantic validation error: {validation_error}")
            raise HTTPException(status_code=422, detail=str(validation_error))
        
        logger.info(f"Received Google auth request with token length: {len(auth_request.google_token) if auth_request.google_token else 0}")
        logger.info(f"User info keys: {list(auth_request.user_info.keys()) if auth_request.user_info else 'None'}")
        
        # Google ID 토큰 검증
        try:
            # 실제 Google 토큰 검증은 여기서 수행해야 함
            # 현재는 프론트엔드에서 받은 정보를 신뢰
            user_info = {
                'user_id': auth_request.user_info.get('id'),
                'email': auth_request.user_info.get('email'),
                'name': auth_request.user_info.get('name'),
                'picture': auth_request.user_info.get('picture', '')
            }
            logger.info(f"Processed user info: {user_info}")
        except Exception as token_error:
            logger.error(f"Token verification error: {token_error}")
            raise HTTPException(status_code=401, detail="Invalid Google token")
        
        if not user_info['user_id']:
            raise HTTPException(status_code=401, detail="Invalid user info")
        
        # 화이트리스트 확인
        is_whitelisted = await check_whitelist(user_info['email'])
        if not is_whitelisted:
            raise HTTPException(
                status_code=403, 
                detail="베타 참여 승인이 필요합니다. 먼저 베타 신청을 완료해주세요."
            )
        
        # 기존 사용자인지 확인
        existing_user = await beta_manager.get_user_by_google_id(user_info['user_id'])
        if existing_user:
            user_data = existing_user
        else:
            # 새 베타 사용자 등록 (화이트리스트 승인된 사용자)
            user_data = await beta_manager.register_beta_user(user_info)
        
        return {
            "success": True, 
            "user_id": user_data['user_id'],
            "user": {
                "user_id": user_data['user_id'],
                "email": user_data['email'],
                "name": user_data['name'],
                "picture": user_data.get('picture', ''),
                "onboarding_completed": user_data.get('onboarding_completed', False)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Google auth error: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")

# 사용자 프로필 및 온보딩 API
@app.get("/api/user/profile")
async def get_user_profile(user_id: str = Header(alias="X-User-Id")):
    """사용자 프로필 조회"""
    try:
        user_profile = await beta_manager.get_user_profile(user_id)
        
        if not user_profile:
            raise HTTPException(status_code=404, detail="User not found")
        
        return user_profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user profile")

# 온보딩 데이터 모델
class OnboardingRequest(BaseModel):
    interests: List[str]
    nickname: str

@app.post("/api/user/onboarding")
async def complete_onboarding(
    request: Request,
    user_id: str = Header(alias="X-User-Id")
):
    """온보딩 완료"""
    try:
        # 원시 요청 데이터 로깅
        body = await request.body()
        logger.info(f"Onboarding raw body: {body.decode('utf-8') if body else 'Empty'}")
        
        # JSON 파싱
        try:
            request_data = await request.json()
            logger.info(f"Onboarding parsed data: {request_data}")
        except Exception as parse_error:
            logger.error(f"Onboarding JSON parsing error: {parse_error}")
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Pydantic 모델 검증
        try:
            onboarding_data = OnboardingRequest(**request_data)
        except Exception as validation_error:
            logger.error(f"Onboarding validation error: {validation_error}")
            raise HTTPException(status_code=422, detail=str(validation_error))
        
        success = await beta_manager.complete_onboarding(
            user_id,
            {
                "interests": onboarding_data.interests,
                "nickname": onboarding_data.nickname
            }
        )
        
        if success:
            return {"success": True, "message": "Onboarding completed successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to complete onboarding")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing onboarding: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete onboarding")

# 에이전트 관리 데이터 모델
class AgentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    tags: List[str] = []
    color: Optional[str] = "#3B82F6"
    icon: Optional[str] = "🤖"

class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    color: Optional[str] = None
    icon: Optional[str] = None

# 에이전트 관리 API
@app.get("/api/agents")
async def list_agents(user_id: str = Header(..., alias="X-User-Id")):
    """사용자의 모든 에이전트 목록 조회"""
    try:
        agents_ref = db.collection('agents').where('userId', '==', user_id)
        agents = []
        for doc in agents_ref.stream():
            agent_data = doc.to_dict()
            agent_data['id'] = doc.id
            agents.append(agent_data)
        
        return agents
    except Exception as e:
        logger.error(f"Error fetching agents for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch agents")

@app.post("/api/agents")
async def create_agent(agent_data: AgentCreateRequest, user_id: str = Header(..., alias="X-User-Id")):
    """새 에이전트 생성"""
    try:
        agent_ref = db.collection('agents').document()
        agent_doc = {
            'name': agent_data.name,
            'description': agent_data.description,
            'status': 'draft',
            'userId': user_id,
            'createdAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow(),
            'lastAccessedAt': None,
            'totalRuns': 0,
            'successfulRuns': 0,
            'lastRunAt': None,
            'tags': agent_data.tags,
            'color': agent_data.color,
            'icon': agent_data.icon,
            'finalPrompt': '',
        }
        
        agent_ref.set(agent_doc)
        agent_doc['id'] = agent_ref.id
        
        logger.info(f"Created agent {agent_ref.id} for user {user_id}")
        return agent_doc
        
    except Exception as e:
        logger.error(f"Error creating agent for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create agent")

@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str, user_id: str = Header(..., alias="X-User-Id")):
    """특정 에이전트 상세 정보 조회"""
    try:
        agent_ref = db.collection('agents').document(agent_id)
        agent_doc = agent_ref.get()
        
        if not agent_doc.exists:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent_data = agent_doc.to_dict()
        
        # 권한 확인
        if agent_data.get('userId') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        agent_data['id'] = agent_id
        return agent_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch agent")

@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, agent_data: AgentUpdateRequest, user_id: str = Header(..., alias="X-User-Id")):
    """에이전트 정보 업데이트"""
    try:
        agent_ref = db.collection('agents').document(agent_id)
        agent_doc = agent_ref.get()
        
        if not agent_doc.exists:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        current_data = agent_doc.to_dict()
        if current_data.get('userId') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # 업데이트할 필드만 추출
        update_data = {}
        for field, value in agent_data.dict(exclude_unset=True).items():
            update_data[field] = value
        
        update_data['updatedAt'] = datetime.utcnow()
        
        agent_ref.update(update_data)
        logger.info(f"Updated agent {agent_id} for user {user_id}")
        
        return {"message": "Agent updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update agent")

@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, user_id: str = Header(..., alias="X-User-Id")):
    """에이전트 삭제"""
    try:
        agent_ref = db.collection('agents').document(agent_id)
        agent_doc = agent_ref.get()
        
        if not agent_doc.exists:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent_data = agent_doc.to_dict()
        if agent_data.get('userId') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        agent_ref.delete()
        logger.info(f"Deleted agent {agent_id} for user {user_id}")
        
        return {"message": "Agent deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete agent")

@app.post("/api/agents/{agent_id}/workspace")
async def create_workspace(agent_id: str, user_id: str = Header(..., alias="X-User-Id")):
    """에이전트를 위한 워크스페이스 생성"""
    try:
        # 에이전트 존재 확인
        agent_ref = db.collection('agents').document(agent_id)
        agent_doc = agent_ref.get()
        
        if not agent_doc.exists:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent_data = agent_doc.to_dict()
        if agent_data.get('userId') != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # 워크스페이스 세션 생성
        session_id = str(uuid.uuid4())
        workspace_ref = db.collection('workspaces').document(session_id)
        
        workspace_data = {
            'sessionId': session_id,
            'agentId': agent_id,
            'userId': user_id,
            'status': 'active',
            'createdAt': datetime.utcnow(),
            'lastActivityAt': datetime.utcnow(),
            'messages': [],
            'currentStep': 'planning',
            'progress': 0.0
        }
        
        workspace_ref.set(workspace_data)
        
        # 에이전트 접근 시간 업데이트
        agent_ref.update({
            'lastAccessedAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        })
        
        logger.info(f"Created workspace {session_id} for agent {agent_id}")
        
        return {
            'sessionId': session_id,
            'agentId': agent_id,
            'wsUrl': f'/workspace/{user_id}',
            'status': 'active'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating workspace for agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create workspace")

@app.get("/api/workspace/{session_id}/restore")
async def restore_workspace(session_id: str):
    """기존 워크스페이스 상태 복원"""
    try:
        workspace_ref = db.collection('workspaces').document(session_id)
        workspace_doc = workspace_ref.get()
        
        if not workspace_doc.exists:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        workspace_data = workspace_doc.to_dict()
        workspace_data['sessionId'] = session_id
        
        # 마지막 활동 시간 업데이트
        workspace_ref.update({
            'lastActivityAt': datetime.utcnow()
        })
        
        return workspace_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring workspace {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to restore workspace")

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(user_id: str = Header(..., alias="X-User-Id")):
    """대시보드 요약 통계"""
    try:
        agents_ref = db.collection('agents').where('userId', '==', user_id)
        agents = []
        for doc in agents_ref.stream():
            agents.append(doc.to_dict())
        
        total_agents = len(agents)
        active_agents = len([a for a in agents if a.get('status') == 'active'])
        total_runs = sum(a.get('totalRuns', 0) for a in agents)
        successful_runs = sum(a.get('successfulRuns', 0) for a in agents)
        success_rate = round((successful_runs / total_runs) * 100) if total_runs > 0 else 0
        
        return {
            'totalAgents': total_agents,
            'activeAgents': active_agents,
            'totalRuns': total_runs,
            'successRate': f"{success_rate}%"
        }
        
    except Exception as e:
        logger.error(f"Error fetching dashboard stats for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

# 정적 파일 서빙 (프론트엔드)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    # 정적 파일들을 /assets 경로로 마운트 (CSS, JS 등)
    app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")
    logger.info(f"Static assets mounted from: {static_dir}")

from fastapi.responses import FileResponse

@app.get("/")
async def root():
    """루트 엔드포인트 - 메인 페이지 직접 서빙"""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    else:
        return {"message": "AI Agent Platform", "error": "index.html not found"}

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting AI Agent Platform in Kubernetes-native mode")
    
    # 서버 시작
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )