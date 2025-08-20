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
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
import google.cloud.firestore as firestore
from auth import auth_manager

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
    
    logger.info("Starting AI Agent Platform in Kubernetes-native mode")
    
    # 서버 시작
    port = int(os.getenv('PORT', 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )