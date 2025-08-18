# main.py
import os
import uuid
import json
import traceback # 상세한 에러 로그를 위해 추가
import subprocess  # Docker 컨테이너 실행을 위한 subprocess
from fastapi import FastAPI, HTTPException, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
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

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 프론트엔드 주소
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 환경 변수 ---
# GCP 환경 변수
PROJECT_ID = os.environ.get("PROJECT_ID", "ai-agent-platform-469401")
REGION = os.environ.get("REGION", "asia-northeast3")


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

class ConversationRequest(BaseModel):
    conversationId: Optional[str] = None
    message: str


# --- API 엔드포인트 ---

@app.get("/")
def read_root():
    return {"status": "ok", "service": "api-server"}

@app.post("/api/conversation")
async def conversation(request: ConversationRequest, x_user_id: str = Header(...)):
    """프론트엔드와의 Claude Code CLI 대화형 에이전트 생성 API"""
    try:
        # 새로운 conversation ID 생성 (필요시)
        conversation_id = request.conversationId or str(uuid.uuid4())
        
        # Firestore에서 대화 기록 조회/생성
        convo_ref = db.collection('conversations').document(conversation_id)
        convo_doc = convo_ref.get()
        
        if not convo_doc.exists:
            # 새로운 대화 시작
            convo_ref.set({
                "messages": [],
                "createdAt": firestore.SERVER_TIMESTAMP,
                "context": "agent_creation"  # 에이전트 생성 대화임을 표시
            })
            conversation_history = []
        else:
            conversation_history = convo_doc.to_dict().get("messages", [])
        
        # 사용자 메시지를 대화 기록에 추가 (timestamp는 나중에 별도 처리)
        user_message = {
            "role": "user",
            "content": request.message,
            "timestamp": None  # 임시로 None, 나중에 실제 시간으로 교체
        }
        conversation_history.append(user_message)
        
        # Claude Code CLI 호출을 위한 프롬프트 구성
        prompt = build_agent_creation_prompt(conversation_history, request.message)
        
        print(f"[{conversation_id}] Claude Code CLI 호출 시작...")
        
        # Docker 컨테이너에서 Claude Code CLI 실행
        import subprocess
        container_name = f"claude-{uuid.uuid4().hex[:8]}"
        
        # 프롬프트 이스케이프 처리
        escaped_prompt = prompt.replace('"', '\\"').replace('\n', '\\n').replace('\\', '\\\\')
        
        command = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory=1g", "--cpus=1",
            # "--network=none",  # 임시로 네트워크 허용 (claude-cli 설치용)
            "-i",
            "python:3.11-slim",  # 임시로 기본 이미지 사용
            "sh", "-c", f'python -c "import json; print(json.dumps({{\\"result\\": \\"테스트 응답: {escaped_prompt[:50]}...\\"}}));"'
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120  # Docker 컨테이너는 시간이 더 필요
        )
        
        if result.returncode != 0:
            print(f"[{conversation_id}] Claude Code CLI 오류: {result.stderr}")
            raise HTTPException(status_code=500, detail="Claude Code CLI 호출 실패")
        
        # Claude 응답 파싱
        try:
            claude_output = json.loads(result.stdout)
            # Claude Code CLI의 JSON 응답에서 실제 텍스트 추출
            response_text = claude_output.get("result", claude_output.get("content", result.stdout))
            print(f"[{conversation_id}] Claude 원본 응답: {response_text[:200]}...")
        except json.JSONDecodeError:
            response_text = result.stdout
        
        # 응답에서 상태, 컴포넌트 등 추출
        response_data = parse_claude_response(response_text)
        
        # 어시스턴트 메시지를 대화 기록에 추가 (timestamp는 나중에 별도 처리)
        assistant_message = {
            "role": "assistant", 
            "content": response_data.get("text", response_text),
            "timestamp": None,  # 임시로 None
            "metadata": {
                "status": response_data.get("status"),
                "component": response_data.get("component"),
                "agentCreated": response_data.get("agentCreated", False)
            }
        }
        conversation_history.append(assistant_message)
        
        # Firestore 업데이트 (ArrayUnion 사용)
        from datetime import datetime
        current_time = datetime.utcnow()
        
        # timestamp 설정
        user_message["timestamp"] = current_time
        assistant_message["timestamp"] = current_time
        
        # 새로운 메시지들만 추가
        convo_ref.update({
            "messages": firestore.ArrayUnion([user_message, assistant_message]),
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        
        print(f"[{conversation_id}] Claude Code CLI 응답 처리 완료")
        
        return {
            "conversationId": conversation_id,
            "text": response_data.get("text", response_text),
            "status": response_data.get("status"),
            "component": response_data.get("component"),
            "agentCreated": response_data.get("agentCreated", False)
        }
        
    except subprocess.TimeoutExpired:
        # 타임아웃 시 컨테이너 강제 종료
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        print(f"[{conversation_id}] Claude Code CLI 타임아웃")
        raise HTTPException(status_code=408, detail="Claude Code CLI 응답 타임아웃")
    except Exception as e:
        print(f"--- 에러 발생: conversation API ---")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

def build_agent_creation_prompt(conversation_history: list, current_message: str) -> str:
    """에이전트 생성을 위한 Claude Code CLI 프롬프트 구성"""
    
    # 대화 컨텍스트 구성
    context = "당신은 사용자가 자동화 에이전트를 생성할 수 있도록 도와주는 AI 어시스턴트입니다.\n"
    context += "사용자와 대화하여 에이전트의 목적, 스케줄, 작업 내용을 단계별로 정의하고,\n"
    context += "최종적으로 실행 가능한 자연어 에이전트 스크립트(finalAgentPrompt)를 생성해야 합니다.\n\n"
    
    # 이전 대화 기록 추가
    if conversation_history:
        context += "이전 대화 내용:\n"
        for msg in conversation_history[-5:]:  # 최근 5개 메시지만
            role = "사용자" if msg["role"] == "user" else "어시스턴트"
            context += f"{role}: {msg['content']}\n"
    
    context += f"\n현재 사용자 메시지: {current_message}\n\n"
    context += """응답 시 다음 형식을 사용하세요:
- 일반 응답은 그대로 작성
- 상태 표시가 필요하면: [상태 표시: 텍스트]
- UI 컴포넌트가 필요하면: [UI 컴포넌트: 타입] HTML내용 [/UI 컴포넌트]
- 에이전트 생성이 완료되면: [에이전트 생성 완료]

사용자와 자연스럽게 대화하며 에이전트 생성을 도와주세요."""
    
    return context

def parse_claude_response(response_text: str) -> dict:
    """Claude 응답에서 상태, 컴포넌트 등을 추출"""
    result = {"text": response_text}
    
    # 상태 표시 추출
    import re
    status_match = re.search(r'\[상태 표시: ([^\]]+)\]', response_text)
    if status_match:
        result["status"] = status_match.group(1)
        result["text"] = response_text.replace(status_match.group(0), "").strip()
    
    # UI 컴포넌트 추출
    component_match = re.search(r'\[UI 컴포넌트: ([^\]]+)\](.*?)\[/UI 컴포넌트\]', response_text, re.DOTALL)
    if component_match:
        result["component"] = {
            "type": component_match.group(1),
            "html": component_match.group(2).strip()
        }
        result["text"] = response_text.replace(component_match.group(0), "").strip()
    
    # 에이전트 생성 완료 확인
    if "[에이전트 생성 완료]" in response_text:
        result["agentCreated"] = True
        result["text"] = response_text.replace("[에이전트 생성 완료]", "").strip()
    
    return result

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
async def run_agent(agent_id: str, background_tasks: BackgroundTasks, x_user_id: str = Header(...)):
    """에이전트 실행을 요청하고 백그라운드에서 Docker 컨테이너로 실행합니다."""
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

    # 3. 백그라운드 작업으로 Docker 컨테이너에서 실행
    background_tasks.add_task(
        execute_agent_in_docker,
        execution_id,
        agent_data.get("prompt", ""),
        agent_data.get("requiredPackages", [])
    )

    return {"message": "Agent execution request accepted", "executionId": execution_id}

def execute_agent_in_docker(execution_id: str, prompt: str, required_packages: List[str]):
    """Docker 컨테이너에서 에이전트를 실행하는 백그라운드 함수"""
    execution_ref = db.collection('executions').document(execution_id)
    print(f"[{execution_id}] 백그라운드 Docker 실행 시작")
    
    try:
        # 상태를 preparing으로 업데이트
        print(f"[{execution_id}] 상태를 'preparing'으로 업데이트")
        execution_ref.update({"status": "preparing"})
        
        # Docker 컨테이너 이름 생성
        container_name = f"agent-{execution_id[:8]}"
        
        # 패키지 설치 명령 구성
        package_install = ""
        if required_packages:
            package_list = " ".join(required_packages)
            package_install = f"pip install {package_list} && "
        
        # 프롬프트 이스케이프 처리
        escaped_prompt = prompt.replace('"', '\\"').replace('\n', '\\n').replace('\\', '\\\\')
        
        print(f"[{execution_id}] Docker 컨테이너 실행: {container_name}")
        
        # 상태를 running으로 업데이트
        execution_ref.update({"status": "running"})
        
        # Docker 명령 구성
        command = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory=1g", "--cpus=1",
            # "--network=none",  # 임시로 네트워크 허용 (claude-cli 설치용)
            "-i",
            "python:3.11-slim",
            "sh", "-c", f'python -c "import json; print(json.dumps({{\\"result\\": \\"에이전트 실행 테스트: {escaped_prompt[:50]}...\\"}}));"'
        ]
        
        # Docker 컨테이너 실행
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600  # 10분 타임아웃
        )
        
        print(f"[{execution_id}] Docker 실행 완료. Return Code: {result.returncode}")
        print(f"[{execution_id}] stdout: {result.stdout[:500]}...")
        print(f"[{execution_id}] stderr: {result.stderr[:500]}...")
        
        # 결과 처리
        if result.returncode == 0 and result.stdout:
            # 성공
            print(f"[{execution_id}] 실행 성공")
            try:
                output_data = json.loads(result.stdout)
                execution_result = output_data.get("result", result.stdout)
                token_usage = output_data.get("usage", {})
            except json.JSONDecodeError:
                execution_result = result.stdout
                token_usage = {}
                
            final_update = {
                "status": "success",
                "endTime": firestore.SERVER_TIMESTAMP,
                "result": execution_result,
                "executionSteps": ["Docker 컨테이너에서 에이전트 실행 완료"],
                "tokenUsage": {
                    "inputTokens": token_usage.get("input_tokens", 0),
                    "outputTokens": token_usage.get("output_tokens", 0)
                }
            }
            execution_ref.update(final_update)
            print(f"[{execution_id}] 성공 상태를 Firestore에 기록")
        else:
            # 실패
            print(f"[{execution_id}] 실행 실패")
            error_message = result.stderr or result.stdout or "알 수 없는 오류가 발생했습니다."
            execution_ref.update({
                "status": "error",
                "endTime": firestore.SERVER_TIMESTAMP,
                "errorMessage": error_message
            })
            print(f"[{execution_id}] 실패 상태를 Firestore에 기록")
            
    except subprocess.TimeoutExpired:
        # 타임아웃 처리
        print(f"[{execution_id}] 타임아웃 발생, 컨테이너 강제 종료")
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        execution_ref.update({
            "status": "error",
            "endTime": firestore.SERVER_TIMESTAMP,
            "errorMessage": "실행 시간 초과로 인한 타임아웃"
        })
    except Exception as e:
        # 예외 처리
        print(f"[{execution_id}] 예외 발생: {str(e)}")
        traceback.print_exc()
        execution_ref.update({
            "status": "error",
            "endTime": firestore.SERVER_TIMESTAMP,
            "errorMessage": f"예상치 못한 오류: {str(e)}"
        })

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
