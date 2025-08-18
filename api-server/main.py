# main.py
import os
import uuid
import traceback # 상세한 에러 로그를 위해 추가
import httpx     # 실행기 서비스 호출을 위한 비동기 HTTP 클라이언트
from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Any

import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase 초기화 ---
try:
    print("API 서버: Firebase 앱 초기화를 시도합니다...")
    firebase_admin.initialize_app()
    print("API 서버: Firebase 앱이 성공적으로 초기화되었습니다.")
except Exception as e:
    if not firebase_admin._apps:
        print(f"치명적 오류: Firebase 초기화에 실패했습니다: {e}")
    else:
        print("API 서버: Firebase 앱이 이미 초기화되어 있습니다.")

db = firestore.client()
app = FastAPI()

# --- 환경 변수 ---
# 실행기 서비스의 주소를 환경 변수에서 읽어오되, 없으면 로컬 주소를 기본값으로 사용
RUNNER_URL = os.environ.get("RUNNER_URL", "http://127.0.0.1:8081/execute")


# --- 데이터 모델 (Pydantic) - 최종 데이터 구조 반영 ---
class Schedule(BaseModel):
    frequency: str = Field(..., example="weekly")
    time: str = Field(..., example="09:00")
    timezone: str = Field(..., example="Asia/Seoul")
    enabled: bool = True

class AgentCreate(BaseModel):
    name: str = Field(..., example="주간 뉴스 분석 에이전트")
    prompt: str = Field(..., example="매주 월요일 아침 9시에 특정 주식에 대한 뉴스를 요약해줘.")
    requiredPackages: Optional[List[str]] = Field(default_factory=list, example=["pandas==2.2.2"])

class Agent(BaseModel):
    id: str
    name: str
    prompt: str
    userId: str
    createdAt: Any
    lastRun: Optional[Any] = None
    status: str
    totalTokenUsage: dict
    schedule: Schedule
    requiredPackages: Optional[List[str]] = []

class MessagePart(BaseModel):
    type: str
    data: Any

class ConversationMessage(BaseModel):
    role: str
    content: str
    parts: List[MessagePart]


# --- API 엔드포인트 ---

@app.get("/")
def read_root():
    return {"status": "ok", "service": "api-server"}

@app.post("/agents", response_model=Agent, status_code=201)
async def create_agent(agent_data: AgentCreate, x_user_id: str = Header(...)):
    """새로운 에이전트를 생성합니다."""
    try:
        agent_id = str(uuid.uuid4())
        agent_ref = db.collection('agents').document(agent_id)

        new_agent = {
            "name": agent_data.name,
            "prompt": agent_data.prompt,
            "userId": x_user_id,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "lastRun": None,
            "status": 'active',
            "totalTokenUsage": {"inputTokens": 0, "outputTokens": 0},
            "schedule": {
                "frequency": 'weekly',
                "time": "09:00",
                "timezone": "Asia/Seoul",
                "enabled": True
            },
            "requiredPackages": agent_data.requiredPackages
        }
        
        agent_ref.set(new_agent)
        
        created_doc = agent_ref.get()
        if not created_doc.exists:
             raise HTTPException(status_code=500, detail="Failed to retrieve agent after creation.")

        return {"id": created_doc.id, **created_doc.to_dict()}

    except Exception as e:
        print(f"--- 에러 발생: create_agent ---")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")


@app.get("/agents", response_model=List[Agent])
async def get_agents(x_user_id: str = Header(...)):
    """현재 사용자의 모든 에이전트 목록을 조회합니다."""
    agents_ref = db.collection('agents').where('userId', '==', x_user_id)
    agents = []
    for doc in agents_ref.stream():
        agent_data = doc.to_dict()
        agent_data['id'] = doc.id
        agents.append(agent_data)
    return agents

@app.get("/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, x_user_id: str = Header(...)):
    """특정 에이전트의 상세 정보를 조회합니다."""
    agent_ref = db.collection('agents').document(agent_id)
    doc = agent_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent_data = doc.to_dict()
    if agent_data['userId'] != x_user_id:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    return {"id": doc.id, **agent_data}


@app.post("/agents/{agent_id}/conversations")
async def add_conversation_message(agent_id: str, message: ConversationMessage, x_user_id: str = Header(...)):
    """에이전트 생성 대화에 메시지를 추가하고, 어시스턴트의 응답을 받습니다."""
    session_id = "default_session" # TODO: 세션 관리 기능 추가 시 동적으로 생성
    convo_ref = db.collection('agents').document(agent_id).collection('conversations').document(session_id)
    
    user_message_data = {
        "role": "user",
        "content": message.content,
        "parts": [part.dict() for part in message.parts],
        "timestamp": firestore.SERVER_TIMESTAMP,
        "tokenUsage": {"inputTokens": 0, "outputTokens": 0} # 실제로는 LLM API 호출 후 업데이트
    }
    
    # merge=True는 문서가 없을 경우 생성하고, 있을 경우 필드를 병합합니다.
    convo_ref.set({"messages": firestore.ArrayUnion([user_message_data]), "updatedAt": firestore.SERVER_TIMESTAMP}, merge=True)

    # TODO: 실제 LLM API 호출 로직으로 대체 필요
    assistant_response = {
        "role": "assistant",
        "content": f"'{message.content}'라고 말씀하셨군요. 알겠습니다.",
        "parts": [{"type": "text", "data": f"'{message.content}'라고 말씀하셨군요. 알겠습니다."}],
        "timestamp": firestore.SERVER_TIMESTAMP,
        "tokenUsage": {"inputTokens": 10, "outputTokens": 20} # 예시 값
    }
    convo_ref.update({"messages": firestore.ArrayUnion([assistant_response])})

    return assistant_response


@app.post("/agents/{agent_id}/run", status_code=202)
async def run_agent(agent_id: str, x_user_id: str = Header(...)):
    """에이전트 실행을 요청하고 실행기(Runner) 서비스를 호출합니다."""
    # 1. 에이전트 존재 및 소유권 확인
    agent_ref = db.collection('agents').document(agent_id)
    agent_doc = agent_ref.get()
    if not agent_doc.exists or agent_doc.to_dict().get('userId') != x_user_id:
        raise HTTPException(status_code=404, detail="Agent not found or permission denied")

    agent_data = agent_doc.to_dict()

    # 2. executions 컬렉션에 실행 기록 생성
    execution_id = str(uuid.uuid4())
    execution_ref = db.collection('executions').document(execution_id)
    
    execution_data = {
        "agentId": agent_id,
        "startTime": firestore.SERVER_TIMESTAMP,
        "endTime": None,
        "status": 'queued', # 초기 상태는 'queued' (대기열)
        "result": None,
        "errorMessage": None,
        "executionSteps": [],
        "tokenUsage": {"inputTokens": 0, "outputTokens": 0}
    }
    execution_ref.set(execution_data)

    # 3. 실행기(Runner) 서비스에 비동기 요청 전송
    payload = {
        "agentId": agent_id,
        "prompt": agent_data.get("prompt"),
        "executionId": execution_id,
        "requiredPackages": agent_data.get("requiredPackages", [])
    }
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"실행기({RUNNER_URL}) 호출. executionId: {execution_id}")
            response = await client.post(RUNNER_URL, json=payload, timeout=10)
            response.raise_for_status() # 2xx 응답 코드가 아니면 에러 발생
        except httpx.RequestError as e:
            print(f"--- 에러 발생: 실행기 호출 실패 ---")
            traceback.print_exc()
            # 실패 시 execution 상태를 error로 업데이트
            execution_ref.update({"status": "error", "errorMessage": f"Failed to trigger agent runner: {e}"})
            raise HTTPException(status_code=500, detail="Could not start agent execution.")

    return {"message": "Agent execution request accepted", "executionId": execution_id}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
