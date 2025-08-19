#!/usr/bin/env python3
"""
AI Agent Platform - WebSocket Based API Server
단순화된 아키텍처: 사용자는 개별 가상환경에서 Claude Code CLI와 Python 패키지를 이용하여 에이전트를 설계하고 구동
"""

import asyncio
import json
import uuid
import logging
import subprocess
import docker
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
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import google.cloud.firestore as firestore
from auth import auth_manager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase
db = firestore.Client()

# Docker client
docker_client = docker.from_env()

class UserWorkspace:
    """사용자별 독립 워크스페이스 관리"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.container = None
        self.container_name = f"workspace-{user_id}"
        
    async def ensure_container(self) -> docker.models.containers.Container:
        """사용자 컨테이너가 없으면 생성, 있으면 재사용"""
        try:
            # 기존 컨테이너 확인
            self.container = docker_client.containers.get(self.container_name)
            self.container.reload()  # 상태 새로고침
            
            if self.container.status != 'running':
                self.container.start()
                # 컨테이너가 완전히 시작될 때까지 대기
                await asyncio.sleep(3)
                logger.info(f"Started existing container for user {self.user_id}")
        except docker.errors.NotFound:
            # 새 컨테이너 생성
            self.container = await self._create_container()
            logger.info(f"Created new container for user {self.user_id}")
        
        # 컨테이너 상태 재확인
        self.container.reload()
        if self.container.status != 'running':
            logger.error(f"Container for user {self.user_id} is not running: {self.container.status}")
            raise Exception(f"Container failed to start: {self.container.status}")
        
        return self.container
    
    async def _create_container(self) -> docker.models.containers.Container:
        """새로운 사용자 컨테이너 생성"""
        # 사용자별 데이터 디렉토리 생성
        data_dir = Path(f"/tmp/workspace-data/{self.user_id}")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        container = docker_client.containers.run(
            image="claude-workspace:latest",
            name=self.container_name,
            command="tail -f /dev/null",  # Keep container running
            environment={
                "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY", "")
            },
            volumes={
                str(data_dir): {"bind": "/workspace", "mode": "rw"}
            },
            mem_limit="1g",
            cpu_count=1,
            detach=True,
            network_mode="bridge",
            working_dir="/workspace"
        )
        
        # 컨테이너가 완전히 시작될 때까지 대기
        await asyncio.sleep(5)
        
        # 컨테이너 상태 확인
        container.reload()
        if container.status != 'running':
            logger.error(f"Failed to start container for user {self.user_id}: {container.status}")
            container.remove()
            raise Exception(f"Container failed to start: {container.status}")
        
        return container
    
    async def send_to_claude(self, message: str, agent_id: str = None) -> str:
        """메시지를 Claude Code CLI로 전달하고 응답 받기"""
        container = await self.ensure_container()
        
        try:
            # 에이전트별 작업 디렉토리 설정 (최소 개선)
            if agent_id:
                workdir = f"/workspace/agent-{agent_id}"
                # 디렉토리 생성 명령어 실행
                container.exec_run(f"mkdir -p {workdir}", user='claude')
            else:
                workdir = "/workspace"
            
            # Claude Code CLI 실행 (print 모드로 비대화형 실행)
            # 메시지를 escape하여 안전하게 전달
            escaped_message = message.replace("'", "'\"'\"'")
            result = container.exec_run(
                cmd=f"claude --print --dangerously-skip-permissions '{escaped_message}'",
                user='claude',
                workdir=workdir
            )
            
            output = result.output.decode('utf-8', errors='ignore')
            
            # 로그에 기록
            logger.info(f"Claude response for user {self.user_id} (agent: {agent_id or 'none'}): {output[:200]}...")
            
            return output
            
        except Exception as e:
            logger.error(f"Error executing Claude command for user {self.user_id}: {e}")
            return f"Error: {str(e)}"
    
    async def cleanup(self):
        """컨테이너 정리"""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
                logger.info(f"Cleaned up container for user {self.user_id}")
            except Exception as e:
                logger.error(f"Error cleaning up container for user {self.user_id}: {e}")

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
            # 컨테이너 정리는 별도 태스크로 처리
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
app = FastAPI(title="AI Agent Platform", version="1.0.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 연결 매니저 초기화
manager = ConnectionManager()

@app.websocket("/workspace/{user_id}")
async def user_workspace(websocket: WebSocket, user_id: str):
    """사용자 전용 워크스페이스 - 개별 컨테이너와 직접 연결"""
    await manager.connect(websocket, user_id)
    
    try:
        # 환영 메시지 전송
        welcome_message = {
            "type": "system",
            "content": f"워크스페이스에 연결되었습니다. Claude Code CLI와 대화를 시작하세요.",
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
                # Claude Code CLI로 메시지 전달
                claude_response = await manager.process_user_message(user_id, user_message)
                
                # 응답 전송
                response_data = {
                    "type": "claude_response",
                    "content": claude_response,
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
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

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
        async for doc in agents_ref.stream():
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
        async for doc in agents_ref.stream():
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

@app.get("/")
async def root():
    """루트 엔드포인트 - 대시보드로 리다이렉트"""
    return {"message": "AI Agent Platform", "dashboard": "/static/dashboard.html"}

# 정적 파일 서빙 (프론트엔드)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")
    logger.info(f"Static files mounted from: {static_dir}")

if __name__ == "__main__":
    import uvicorn
    
    # Docker 이미지 확인
    try:
        docker_client.images.get("claude-workspace:latest")
        logger.info("Claude workspace image found")
    except docker.errors.ImageNotFound:
        logger.error("Claude workspace image not found. Please build it first:")
        logger.error("cd docker/claude-workspace && docker build -t claude-workspace:latest .")
        exit(1)
    
    # 서버 시작
    import os
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )