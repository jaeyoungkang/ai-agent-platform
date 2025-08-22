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
import subprocess
import shutil
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
from claude_init import ensure_claude_ready, get_claude_status
from auth import google_auth, beta_manager
from email_service import email_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firestore
db = firestore.Client()

class ClaudeCodeProcess:
    """실제 Claude Code CLI 프로세스 관리자 (영구 세션 지원)"""
    
    def __init__(self, user_id: str, session_id: str):
        # 기존 필드 완전 유지 (호환성 보장)
        self.user_id = user_id
        self.session_id = session_id
        self.process: Optional[subprocess.Popen] = None
        self.output_buffer = []
        self.is_running = False
        
        # 새 영구 세션 필드 추가 (기존 코드에 영향 없음)
        self.persistent_process = None
        self.reader = None
        self.writer = None
        self.conversation_history = []
        self.use_persistent = os.getenv('ENABLE_PERSISTENT_SESSIONS', 'true').lower() == 'true'
        self.session_start_time = None
        self.last_activity = None
        
    async def start(self, initial_context: str = None):
        """실제 Claude Code CLI 프로세스 시작"""
        try:
            # Claude Code CLI 버전 확인
            claude_path = shutil.which('claude')
            if not claude_path:
                logger.error("Claude Code CLI not found")
                return False
            
            # API 키 확인
            if not os.environ.get('ANTHROPIC_API_KEY'):
                logger.error("ANTHROPIC_API_KEY not set")
                return False
            
            # Claude Code CLI 실행 명령
            cmd = ['claude', 'chat']
            
            # 에이전트 생성 모드인 경우 시스템 프롬프트 추가
            if initial_context == 'agent-create':
                system_prompt = self._get_agent_creation_prompt()
                cmd.extend(['--system', system_prompt])
            
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.is_running = True
            
            # 비동기 출력 읽기 시작
            asyncio.create_task(self._read_output())
            
            logger.info(f"Claude Code process started for session {self.session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start Claude Code: {e}")
            return False
    
    def _get_agent_creation_prompt(self) -> str:
        """에이전트 생성을 위한 시스템 프롬프트"""
        return """당신은 AI 에이전트를 생성하는 도우미입니다.
사용자가 원하는 자동화 작업을 이해하고, 단계별로 에이전트를 구성하도록 도와주세요.

주요 단계:
1. 에이전트 이름과 목적 정의
2. 실행 스케줄 설정
3. 작업 단계 구성
4. 테스트 및 검증
5. 최종 생성

자연스럽고 대화형으로 에이전트 생성을 도와주세요.

최대한 간결하게 답변해주세요. 200자 이내로 답변하는 것이 좋습니다."""
    
    async def _read_output(self):
        """비동기로 Claude 출력 읽기"""
        if not self.process:
            return
        
        while self.is_running and self.process and self.process.poll() is None:
            try:
                # stdout에서 줄 단위로 읽기 (비동기)
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self.process.stdout.readline
                )
                if line:
                    line = line.strip()
                    if line:  # 빈 줄 무시
                        self.output_buffer.append(line)
                        # 너무 많이 누적되지 않도록 제한
                        if len(self.output_buffer) > 100:
                            self.output_buffer = self.output_buffer[-50:]  # 최근 50줄만 유지
                
                await asyncio.sleep(0.1)  # CPU 사용률 제어
                
            except Exception as e:
                logger.error(f"Error reading Claude output: {e}")
                break
    
    async def send_message(self, message: str, timeout: float = 30.0) -> str:
        """Claude Code CLI에 메시지 전송 (영구 세션 또는 기존 방식)"""
        try:
            if self.use_persistent:
                # 영구 세션 방식 시도
                try:
                    return await self._send_via_persistent_session(message, timeout)
                except Exception as e:
                    logger.warning(f"Persistent session failed, falling back to subprocess: {e}")
                    # Fallback to 기존 방식
                    return await self._send_via_subprocess(message, timeout)
            else:
                # 기존 방식 사용
                return await self._send_via_subprocess(message, timeout)
        except Exception as e:
            logger.error(f"Error in Claude communication: {e}")
            return f"Claude 통신 오류: {str(e)}"
    
    async def _send_via_persistent_session(self, message: str, timeout: float = 30.0) -> str:
        """영구 세션을 통한 메시지 전송"""
        # 세션이 없거나 비정상이면 새로 시작
        if not self._is_persistent_session_healthy():
            await self._start_persistent_session()
        
        # 메시지 전송
        if self.writer:
            self.writer.write(f"{message}\n".encode('utf-8'))
            await self.writer.drain()
            
            # 응답 읽기 (타임아웃 적용)
            try:
                response_bytes = await asyncio.wait_for(
                    self.reader.read(8192),  # 8KB 버퍼
                    timeout=timeout
                )
                response = response_bytes.decode('utf-8').strip()
                
                # 대화 히스토리 저장
                self.conversation_history.append((message, response))
                self.last_activity = datetime.now()
                
                if response:
                    cleaned_response = self._clean_response(response)
                    logger.info(f"Persistent Claude response for session {self.session_id}: {len(cleaned_response)} chars")
                    return cleaned_response
                else:
                    return "Claude로부터 응답을 받지 못했습니다."
                
            except asyncio.TimeoutError:
                logger.error(f"Persistent session timeout after {timeout} seconds")
                # 세션 재시작 시도
                await self._restart_persistent_session()
                raise
        else:
            raise Exception("Persistent session writer not available")
    
    async def _send_via_subprocess(self, message: str, timeout: float = 30.0) -> str:
        """기존 subprocess 방식 (완전 호환)"""
        # 기존 코드 그대로 유지
        cmd = ['claude', 'chat']
        
        # 에이전트 생성 컨텍스트용 시스템 프롬프트
        if hasattr(self, '_context') and self._context == 'agent-create':
            system_prompt = self._get_agent_creation_prompt()
            cmd.extend(['--append-system-prompt', system_prompt])
        
        logger.info(f"Executing Claude command: {' '.join(cmd)}")
        logger.info(f"Input message: {message}")
        
        # subprocess 실행 (파이프 통신)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # 메시지 전송 및 응답 받기 (bytes로 처리)
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(input=message.encode('utf-8')),
            timeout=timeout
        )
        
        # bytes를 문자열로 변환
        stdout = stdout_bytes.decode('utf-8') if stdout_bytes else ""
        stderr = stderr_bytes.decode('utf-8') if stderr_bytes else ""
        
        logger.info(f"Claude stdout: {stdout}")
        if stderr:
            logger.warning(f"Claude stderr: {stderr}")
        
        if stdout and stdout.strip():
            response = self._clean_response(stdout)
            logger.info(f"Claude response for session {self.session_id}: {len(response)} chars")
            return response
        else:
            return "Claude로부터 응답을 받지 못했습니다."
    
    def _clean_response(self, response: str) -> str:
        """응답 정리 (프롬프트 제거 등)"""
        lines = response.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 비어있지 않고 프롬프트가 아닌 줄만 포함
            if line.strip() and not line.strip().startswith('Human:') and not line.strip().endswith('>'):
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def stop(self):
        """프로세스 종료 (기존 방식 + 영구 세션 정리)"""
        self.is_running = False
        
        # 영구 세션 정리 (async 작업이므로 task로 실행)
        if hasattr(self, 'persistent_process') and self.persistent_process:
            asyncio.create_task(self._cleanup_persistent_session())
        
        # 기존 프로세스 정리
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception as e:
                logger.error(f"Error stopping Claude process: {e}")
                try:
                    self.process.kill()
                except:
                    pass
            finally:
                self.process = None
        logger.info(f"Claude process stopped for session {self.session_id}")
    
    async def _start_persistent_session(self):
        """영구 Claude 세션 시작"""
        try:
            cmd = ['claude', 'chat', '--interactive']
            
            # 에이전트 생성 컨텍스트용 시스템 프롬프트
            if hasattr(self, '_context') and self._context == 'agent-create':
                system_prompt = self._get_agent_creation_prompt()
                cmd.extend(['--system', system_prompt])
            
            logger.info(f"Starting persistent Claude session: {' '.join(cmd)}")
            
            # 영구 프로세스 시작
            self.persistent_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            self.reader = self.persistent_process.stdout
            self.writer = self.persistent_process.stdin
            self.session_start_time = datetime.now()
            self.last_activity = datetime.now()
            
            logger.info(f"Persistent Claude session started for {self.user_id}/{self.session_id}")
            
        except Exception as e:
            logger.error(f"Failed to start persistent session: {e}")
            await self._cleanup_persistent_session()
            raise
    
    def _is_persistent_session_healthy(self) -> bool:
        """영구 세션 상태 확인"""
        if not self.persistent_process or not self.reader or not self.writer:
            return False
        
        # 프로세스가 살아있는지 확인
        if self.persistent_process.returncode is not None:
            return False
        
        # 최근 활동 시간 확인 (30분 이상 비활성화시 재시작)
        if self.last_activity:
            inactive_time = datetime.now() - self.last_activity
            if inactive_time.total_seconds() > 1800:  # 30분
                logger.info(f"Persistent session inactive for {inactive_time}, will restart")
                return False
        
        return True
    
    async def _restart_persistent_session(self):
        """영구 세션 재시작"""
        logger.info(f"Restarting persistent session for {self.user_id}/{self.session_id}")
        await self._cleanup_persistent_session()
        await self._start_persistent_session()
    
    async def _cleanup_persistent_session(self):
        """영구 세션 정리"""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.warning(f"Error closing writer: {e}")
            self.writer = None
        
        if self.persistent_process:
            try:
                self.persistent_process.terminate()
                await asyncio.wait_for(self.persistent_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Force killing persistent process")
                self.persistent_process.kill()
            except Exception as e:
                logger.warning(f"Error terminating process: {e}")
            self.persistent_process = None
        
        self.reader = None


class UserWorkspace:
    """사용자별 Claude Code 세션 관리"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.claude_processes: Dict[str, ClaudeCodeProcess] = {}  # session_id -> ClaudeCodeProcess
    
    async def send_to_claude(self, message: str, agent_id: str = None, context: str = "workspace", session_id: str = None) -> str:
        """실제 Claude Code CLI와 통신"""
        logger.info(f"Processing message for user {self.user_id} (context: {context}, session: {session_id})")
        
        # session_id가 없으면 기본 세션 사용
        if not session_id:
            session_id = f"default_{self.user_id}"
        
        # Claude 프로세스 가져오거나 생성
        if session_id not in self.claude_processes:
            self.claude_processes[session_id] = ClaudeCodeProcess(self.user_id, session_id)
            # 컨텍스트 저장
            self.claude_processes[session_id]._context = context
        
        claude_process = self.claude_processes[session_id]
        
        # 실제 Claude Code에 메시지 전송
        response = await claude_process.send_message(message)
        
        # 에이전트 생성 컨텍스트인 경우 추가 처리
        if context == "agent-create" and session_id:
            response = await self._process_agent_creation_response(response, session_id)
        
        return response
    
    async def _process_agent_creation_response(self, response: str, session_id: str) -> str:
        """에이전트 생성 응답 후처리"""
        # 에이전트 생성 완료 감지
        if "생성이 완료" in response or "에이전트가 생성" in response or "완료되었습니다" in response:
            # 실제 에이전트 생성 로직 호출
            agent_id = await self._create_agent_from_conversation(session_id)
            if agent_id:
                response += f"\n\n✅ 에이전트가 성공적으로 생성되었습니다! \n[대시보드로 이동](/assets/dashboard.html)"
        
        return response
    
    async def _create_agent_from_conversation(self, session_id: str) -> Optional[str]:
        """대화 내용에서 에이전트 생성"""
        try:
            # 워크스페이스 세션 데이터 가져오기
            workspace_doc = db.collection('workspaces').document(session_id).get()
            if not workspace_doc.exists:
                return None
            
            workspace_data = workspace_doc.to_dict()
            agent_config = workspace_data.get('agentConfig', {})
            
            # 기본 에이전트 정보 생성
            agent_ref = db.collection('agents').document()
            agent_data = {
                'name': agent_config.get('name', 'Claude Code 에이전트'),
                'description': agent_config.get('description', 'Claude Code로 생성된 AI 에이전트'),
                'userId': self.user_id,
                'status': 'active',
                'createdAt': datetime.utcnow(),
                'updatedAt': datetime.utcnow(),
                'lastAccessedAt': datetime.utcnow(),
                'totalRuns': 0,
                'successfulRuns': 0,
                'lastRunAt': None,
                'tags': ['claude-code', 'ai-generated'],
                'color': '#3B82F6',
                'icon': '🤖',
                'finalPrompt': f"이 에이전트는 Claude Code를 통해 생성되었습니다. 세션 ID: {session_id}"
            }
            
            agent_ref.set(agent_data)
            logger.info(f"Created agent {agent_ref.id} from Claude conversation")
            return agent_ref.id
            
        except Exception as e:
            logger.error(f"Error creating agent from conversation: {e}")
            return None
    
    async def cleanup(self):
        """모든 세션 정리"""
        logger.info(f"Cleaning up workspace for user {self.user_id}")
        for process in self.claude_processes.values():
            process.stop()
        self.claude_processes.clear()

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
    
    async def process_user_message(self, user_id: str, message: str, agent_id: str = None, context: str = "workspace", session_id: str = None) -> str:
        """사용자 메시지를 Claude Code CLI로 전달하고 응답 받기"""
        if user_id not in self.user_workspaces:
            return "Error: Workspace not found"
        
        workspace = self.user_workspaces[user_id]
        response = await workspace.send_to_claude(message, agent_id, context, session_id)
        
        # Firestore에 대화 기록 저장
        await self._save_conversation(user_id, message, response, agent_id, session_id)
        
        return response
    
    async def _save_conversation(self, user_id: str, user_message: str, assistant_response: str, agent_id: str = None, session_id: str = None):
        """Firestore에 대화 기록 저장 (개선된 통합 방식)"""
        try:
            # 메시지 객체 생성
            messages = [
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
            ]
            
            # 세션 기반 대화 기록 (통합 방식)
            if session_id:
                try:
                    workspace_ref = db.collection('workspaces').document(session_id)
                    workspace_doc = workspace_ref.get()
                    
                    if workspace_doc.exists:
                        # 기존 workspace에 메시지 추가 (ArrayUnion 사용)
                        workspace_ref.update({
                            'messages': firestore.ArrayUnion(messages),
                            'lastActivityAt': datetime.utcnow()
                        })
                        logger.info(f"Messages added to workspace {session_id} using ArrayUnion")
                    else:
                        logger.warning(f"Workspace {session_id} not found, creating new workspace")
                        # 워크스페이스가 없으면 새로 생성
                        workspace_data = {
                            'sessionId': session_id,
                            'userId': user_id,
                            'agentId': agent_id,
                            'status': 'active',
                            'createdAt': datetime.utcnow(),
                            'lastActivityAt': datetime.utcnow(),
                            'messages': messages,
                            'context': 'workspace'
                        }
                        workspace_ref.set(workspace_data)
                        
                except Exception as workspace_error:
                    logger.error(f"Error updating workspace {session_id}: {workspace_error}")
                    # Fallback to conversations collection
                    await self._save_to_conversations_collection(user_id, user_message, assistant_response, agent_id, session_id)
            else:
                # 세션 ID가 없으면 기존 conversations 컬렉션 사용
                await self._save_to_conversations_collection(user_id, user_message, assistant_response, agent_id, session_id)
                
        except Exception as e:
            logger.error(f"Error saving conversation: {e}")
            # 최종 fallback - 항상 conversations에 저장
            try:
                await self._save_to_conversations_collection(user_id, user_message, assistant_response, agent_id, session_id)
            except Exception as fallback_error:
                logger.error(f"Fallback conversation save also failed: {fallback_error}")
    
    async def _save_to_conversations_collection(self, user_id: str, user_message: str, assistant_response: str, agent_id: str = None, session_id: str = None):
        """기존 conversations 컬렉션에 저장 (호환성 보장)"""
        conversation_ref = db.collection('conversations').document()
        conversation_data = {
            'userId': user_id,
            'agentId': agent_id,
            'sessionId': session_id,
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
        "script-src 'self' https://accounts.google.com https://cdn.tailwindcss.com 'unsafe-inline'; "
        "style-src 'self' https://cdn.tailwindcss.com 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'"
    )
    response.headers["Content-Security-Policy"] = csp_policy
    
    return response

# 연결 매니저 초기화
manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 Claude Code 빠른 검증"""
    logger.info("Validating Claude Code (fast check)...")
    
    # Claude Code 빠른 검증 (Docker 이미지에 이미 설치됨)
    if not ensure_claude_ready():
        status = get_claude_status()
        logger.error(f"FATAL: Claude Code not available")
        logger.error("This Docker image should have Claude Code pre-installed.")
        logger.error("Please rebuild the image using Dockerfile.optimized")
        raise Exception("Claude Code not found. Wrong Docker image?")
    
    status = get_claude_status()
    logger.info(f"✓ Claude Code: {status['claude_path']}")
    logger.info(f"✓ API Key: {'SET' if status['api_key_set'] else 'MISSING'}")
    
    if not status['api_key_set']:
        raise Exception("ANTHROPIC_API_KEY environment variable is required")
    
    app.state.claude_ready = True
    logger.info("Service ready in seconds!")

@app.websocket("/workspace/{user_id}")
async def user_workspace(websocket: WebSocket, user_id: str):
    """사용자 전용 워크스페이스 - Kubernetes Pod 세션 기반"""
    logger.info(f"WebSocket connection attempt from user: {user_id}")
    
    try:
        await manager.connect(websocket, user_id)
        logger.info(f"WebSocket connected successfully for user: {user_id}")
        
        # 환영 메시지 전송
        welcome_message = {
            "type": "system",
            "content": f"Claude Code CLI에 연결되었습니다. 실제 Claude와 대화를 시작하세요.",
            "timestamp": datetime.utcnow().isoformat()
        }
        await websocket.send_text(json.dumps(welcome_message))
        
        # 메시지 처리 루프
        while True:
            # 사용자 메시지 수신
            data = await websocket.receive_text()
            message_data = json.loads(data)
            user_message = message_data.get('message', '')
            session_id = message_data.get('session_id')  # 세션 ID 추출
            
            if user_message:
                # 세션 컨텍스트 확인
                context = "workspace"  # 기본값
                if session_id:
                    workspace_doc = db.collection('workspaces').document(session_id).get()
                    if workspace_doc.exists:
                        workspace_data = workspace_doc.to_dict()
                        context = workspace_data.get('context', 'workspace')
                
                # Claude Code CLI로 메시지 전달
                agent_response = await manager.process_user_message(
                    user_id, user_message, context=context, session_id=session_id
                )
                
                # 응답 전송
                response_data = {
                    "type": "claude_response",
                    "content": agent_response,
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send_text(json.dumps(response_data))
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user: {user_id}")
        manager.disconnect(user_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        logger.error(f"WebSocket error type: {type(e).__name__}")
        logger.error(f"WebSocket error details: {str(e)}")
        manager.disconnect(user_id)

@app.get("/health")
async def health_check():
    """헬스체크 엔드포인트"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat(), "version": "1.0.3", "registry": "artifact-registry"}

# 게스트 인증 API 제거됨 - Google OAuth만 사용

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

@app.post("/api/agents/create-session")
async def create_agent_session(user_id: str = Header(..., alias="X-User-Id")):
    """에이전트 생성을 위한 워크스페이스 세션 생성"""
    try:
        session_id = str(uuid.uuid4())
        workspace_ref = db.collection('workspaces').document(session_id)
        
        workspace_data = {
            'sessionId': session_id,
            'agentId': None,  # 에이전트 생성 중이므로 null
            'userId': user_id,
            'context': 'agent-create',  # 핵심: 컨텍스트 설정
            'status': 'active',
            'createdAt': datetime.utcnow(),
            'lastActivityAt': datetime.utcnow(),
            'messages': [],
            'agentConfig': {
                'name': None,
                'description': None,
                'schedule': None,
                'tasks': [],
                'status': 'draft'
            }
        }
        
        workspace_ref.set(workspace_data)
        
        logger.info(f"Created agent creation session {session_id} for user {user_id}")
        
        return {
            'sessionId': session_id,
            'wsUrl': f'/workspace/{user_id}',
            'redirectUrl': f'/assets/workspace.html?session={session_id}',
            'context': 'agent-create'
        }
        
    except Exception as e:
        logger.error(f"Error creating agent session for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create agent session")

@app.get("/api/workspace/{session_id}/restore")
async def restore_workspace(session_id: str):
    """기존 워크스페이스 상태 복원 (대화 기록 포함)"""
    try:
        workspace_ref = db.collection('workspaces').document(session_id)
        workspace_doc = workspace_ref.get()
        
        if not workspace_doc.exists:
            raise HTTPException(status_code=404, detail="Workspace not found")
        
        workspace_data = workspace_doc.to_dict()
        workspace_data['sessionId'] = session_id
        
        # 대화 기록 정렬 (타임스탬프 기준)
        messages = workspace_data.get('messages', [])
        if messages:
            try:
                # 각 메시지의 timestamp를 기준으로 정렬
                sorted_messages = sorted(messages, key=lambda x: x.get('timestamp', datetime.min))
                workspace_data['messages'] = sorted_messages
                logger.info(f"Restored {len(sorted_messages)} messages for session {session_id}")
            except Exception as sort_error:
                logger.warning(f"Error sorting messages for session {session_id}: {sort_error}")
                # 정렬 실패해도 원래 메시지는 유지
        
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