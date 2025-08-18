# runner_main.py
import os
import subprocess
import json
import traceback
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List

import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase 초기화 ---
try:
    print("실행기: Firebase 앱 초기화를 시도합니다...")
    firebase_admin.initialize_app()
    print("실행기: Firebase 앱이 성공적으로 초기화되었습니다.")
except Exception as e:
    if not firebase_admin._apps:
        print(f"치명적 오류: Firebase 초기화에 실패했습니다: {e}")
    else:
        print("실행기: Firebase 앱이 이미 초기화되어 있습니다.")

db = firestore.client()
app = FastAPI()

# --- 데이터 모델 ---
class ExecutionRequest(BaseModel):
    agentId: str
    prompt: str
    executionId: str
    requiredPackages: List[str] = Field(default_factory=list)

# --- 백그라운드 작업 함수 ---
def execute_agent_task(exec_id: str, prompt: str, packages: List[str]):
    """
    실제 에이전트 실행을 담당하는 백그라운드 함수.
    1. 패키지 설치
    2. claude code 실행
    3. 결과 기록
    """
    execution_ref = db.collection('executions').document(exec_id)
    print(f"[{exec_id}] 백그라운드 작업 시작.")

    try:
        # 1. 환경 준비 (패키지 설치)
        print(f"[{exec_id}] 상태를 'preparing'으로 업데이트합니다.")
        try:
            execution_ref.update({"status": "preparing"})
        except Exception as e:
            print(f"[{exec_id}] Firestore 업데이트 실패 (테스트 모드에서는 무시): {e}")

        if packages:
            print(f"[{exec_id}] 다음 패키지를 설치합니다: {packages}")
            subprocess.run(
                ["pip", "install"] + packages,
                check=True,
                capture_output=True,
                text=True
            )
            print(f"[{exec_id}] 패키지 설치 완료.")
        else:
            print(f"[{exec_id}] 추가로 설치할 패키지가 없습니다.")

        # 2. claude code 실행
        print(f"[{exec_id}] 상태를 'running'으로 업데이트합니다.")
        try:
            execution_ref.update({"status": "running"})
        except Exception as e:
            print(f"[{exec_id}] Firestore 업데이트 실패 (테스트 모드에서는 무시): {e}")

        print(f"[{exec_id}] claude code를 다음 프롬프트로 실행합니다: {prompt}")
        
        # --print 모드에서는 프롬프트를 stdin으로 전달해야 합니다.
        command = [
            "claude",
            "--print",
            "--output-format", "json",
            "--permission-mode", "acceptEdits"
        ]
        
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
            input=prompt  # 프롬프트를 stdin으로 전달
        )

        print(f"[{exec_id}] claude code 실행 완료. Return Code: {result.returncode}")
        print(f"[{exec_id}] stdout: {result.stdout}")
        print(f"[{exec_id}] stderr: {result.stderr}")

        # 3. 결과 처리 및 Firestore 업데이트
        if result.returncode == 0 and result.stdout:
            # 성공
            print(f"[{exec_id}] 실행 성공. 결과를 처리합니다.")
            try:
                output_data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                print(f"[{exec_id}] JSON 파싱 실패: {e}")
                output_data = {"summary": result.stdout, "steps": [], "tokenUsage": {}}

            final_update = {
                "status": "success",
                "endTime": firestore.SERVER_TIMESTAMP,
                "result": output_data.get("summary", "결과 요약 없음"),
                "executionSteps": output_data.get("steps", []),
                "tokenUsage": output_data.get("tokenUsage", {})
            }
            try:
                execution_ref.update(final_update)
                print(f"[{exec_id}] Firestore에 성공 상태를 기록했습니다.")
            except Exception as e:
                print(f"[{exec_id}] Firestore 업데이트 실패 (테스트 모드에서는 무시): {e}")
                print(f"[{exec_id}] 로컬 결과: {final_update}")
        else:
            # 실패
            print(f"[{exec_id}] 실행 실패. 에러를 기록합니다.")
            error_message = result.stderr or result.stdout or "알 수 없는 에러가 발생했습니다."
            final_update = {
                "status": "error",
                "endTime": firestore.SERVER_TIMESTAMP,
                "errorMessage": error_message
            }
            try:
                execution_ref.update(final_update)
                print(f"[{exec_id}] Firestore에 에러 상태를 기록했습니다. Stderr: {result.stderr}")
            except Exception as e:
                print(f"[{exec_id}] Firestore 업데이트 실패 (테스트 모드에서는 무시): {e}")
                print(f"[{exec_id}] 로컬 에러 결과: {final_update}")

    except subprocess.CalledProcessError as e:
        error_details = f"패키지 설치 중 에러 발생:\n{e.stderr}"
        print(f"[{exec_id}] {error_details}")
        try:
            execution_ref.update({
                "status": "error",
                "endTime": firestore.SERVER_TIMESTAMP,
                "errorMessage": error_details
            })
        except Exception as e:
            print(f"[{exec_id}] Firestore 업데이트 실패 (테스트 모드에서는 무시): {e}")
            print(f"[{exec_id}] 로컬 에러: {error_details}")
    except Exception as e:
        error_details = f"예상치 못한 오류 발생: {traceback.format_exc()}"
        print(f"[{exec_id}] {error_details}")
        try:
            execution_ref.update({
                "status": "error",
                "endTime": firestore.SERVER_TIMESTAMP,
                "errorMessage": error_details
            })
        except Exception as e:
            print(f"[{exec_id}] Firestore 업데이트 실패 (테스트 모드에서는 무시): {e}")
            print(f"[{exec_id}] 로컬 에러: {error_details}")

# --- API 엔드포인트 ---
@app.post("/execute", status_code=202)
async def execute_agent(request: ExecutionRequest, background_tasks: BackgroundTasks):
    print(f"실행 요청 수신: executionId={request.executionId}")
    background_tasks.add_task(
        execute_agent_task,
        request.executionId,
        request.prompt,
        request.requiredPackages
    )
    return {"status": "accepted", "executionId": request.executionId}

@app.get("/")
def read_root():
    return {"status": "ok", "service": "agent-runner"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8081))
    uvicorn.run(app, host="0.0.0.0", port=port)
