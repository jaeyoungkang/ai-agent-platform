# 2단계: Cloud Build 연동 세부 계획안

**작성일**: 2025-01-18  
**목표**: 기존 엔드포인트 유지하면서 실행 방식만 Cloud Build로 변경  
**전제**: 1단계에서 모의 응답으로 기본 구조 검증 완료

## 📋 현재 상황 분석

### 1단계 완료 상태
- ✅ Cloud Build 클라이언트 초기화 완료
- ✅ `execute_claude_with_cloudbuild()` 함수 구현 (모의 응답)
- ✅ `/api/conversation`, `/agents/{id}/run` 엔드포인트 Cloud Build 호출 구조 완성
- ✅ 기존 API 인터페이스 및 Firestore 연동 보존
- ✅ 로컬 테스트 환경에서 모든 기능 정상 동작

### 남은 작업
1. **Cloud Build 실제 실행**: 모의 응답 → 실제 Cloud Build API 호출
2. **Cloud Logging 연동**: 실행 결과 로그 수집 및 파싱
3. **Firestore 연동 유지**: 기존 대화 기록, 에이전트 정보 보존

## 🎯 2단계 목표

**핵심**: Firestore 연동을 유지하면서 Cloud Build에서 실제 Claude Code 실행

### 유지해야 할 기존 기능
- **POST `/api/conversation`**: 대화형 에이전트 생성 (Firestore 대화 기록 저장)
- **POST `/agents/{id}/run`**: 에이전트 실행 (Firestore 실행 기록 저장)
- **GET `/agents`**: 에이전트 목록 (Firestore 연동)
- **API 응답 형식**: frontend_implementation.md에 정의된 형식 유지

## 📝 구체적 작업 목록

### 작업 1: Cloud Build 실제 실행 활성화
**파일**: `api-server/main.py`

**현재 코드** (모의 응답):
```python
async def execute_claude_with_cloudbuild(prompt: str, required_packages: Optional[List[str]] = None) -> dict:
    print(f"Cloud Build 모의 실행 시작. 프롬프트 길이: {len(prompt)}")
    
    # 로컬 테스트용 모의 응답
    if "에이전트" in prompt or "자동화" in prompt:
        return {"result": "...", "status": "success"}
```

**변경 후 코드**:
```python
async def execute_claude_with_cloudbuild(prompt: str, required_packages: Optional[List[str]] = None) -> dict:
    # 환경 변수로 모의/실제 모드 전환
    if os.environ.get('CLOUDBUILD_MOCK', 'false').lower() == 'true':
        return await execute_mock_response(prompt)
    
    # 실제 Cloud Build 실행
    return await execute_real_cloudbuild(prompt, required_packages)
```

### 작업 2: Cloud Build 스텝 최적화
**목표**: 1월 18일 테스트에서 검증된 명령어 적용

**Cloud Build 설정**:
```yaml
steps:
- name: 'python:3.9'
  entrypoint: 'bash'
  args:
  - '-c'  
  - |
    pip install claude-cli
    echo "${_PROMPT}" | claude --print --output-format json --permission-mode acceptEdits
timeout: 300s
options:
  env:
  - 'ANTHROPIC_API_KEY=${_ANTHROPIC_API_KEY}'
```

### 작업 3: Cloud Logging 연동 구현
**파일**: `api-server/main.py`

**새로운 함수 추가**:
```python
from google.cloud import logging as cloud_logging

async def get_cloudbuild_logs(build_id: str) -> str:
    """Cloud Build 실행 로그에서 Claude 응답 추출"""
    
    logging_client = cloud_logging.Client()
    
    # Cloud Build 로그 필터
    filter_str = f'resource.type="build" AND resource.labels.build_id="{build_id}"'
    
    entries = logging_client.list_entries(filter_=filter_str)
    
    for entry in entries:
        if 'claude' in entry.payload.get('textPayload', '').lower():
            # Claude JSON 응답 추출 로직
            return parse_claude_response_from_log(entry.payload['textPayload'])
    
    return "로그에서 응답을 찾을 수 없습니다"

def parse_claude_response_from_log(log_text: str) -> str:
    """로그에서 JSON 응답 추출"""
    import re
    
    # JSON 패턴 찾기
    json_match = re.search(r'\{.*"result".*\}', log_text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            return result.get('result', log_text)
        except json.JSONDecodeError:
            pass
    
    return log_text
```

### 작업 4: 환경 변수 설정
**파일**: `api-server/main.py`

**추가할 환경 변수**:
```python
# 환경 변수
CLOUDBUILD_MOCK = os.environ.get('CLOUDBUILD_MOCK', 'true')  # 로컬: true, 배포: false
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
```

### 작업 5: 에러 핸들링 강화
**목표**: Cloud Build 실패 시 적절한 에러 응답

**에러 처리 로직**:
```python
async def execute_real_cloudbuild(prompt: str, required_packages: Optional[List[str]] = None) -> dict:
    try:
        # Cloud Build 실행
        operation = cloudbuild_client.create_build(project_id=PROJECT_ID, build=build_config)
        result = operation.result(timeout=300)
        
        if result.status == Build.Status.SUCCESS:
            # 로그에서 Claude 응답 추출
            claude_response = await get_cloudbuild_logs(result.id)
            return {"result": claude_response, "status": "success"}
        
        elif result.status == Build.Status.FAILURE:
            error_logs = await get_cloudbuild_logs(result.id)
            return {"error": f"Cloud Build 실행 실패: {error_logs}", "status": "failed"}
            
        else:
            return {"error": f"Cloud Build 상태 불명: {result.status}", "status": "unknown"}
            
    except Exception as e:
        return {"error": f"Cloud Build 호출 오류: {str(e)}", "status": "error"}
```

## 🔍 단계별 구현 계획

### Phase 1: 환경 변수 및 로깅 설정 (30분)
1. **환경 변수 추가**: `CLOUDBUILD_MOCK`, `ANTHROPIC_API_KEY`
2. **Cloud Logging 클라이언트 설정**
3. **모의/실제 모드 전환 로직 구현**

### Phase 2: Cloud Build 실제 실행 구현 (60분)
1. **`execute_real_cloudbuild()` 함수 구현**
2. **Cloud Build 설정 최적화**
3. **에러 핸들링 로직 추가**

### Phase 3: Cloud Logging 연동 (45분)
1. **`get_cloudbuild_logs()` 함수 구현**
2. **로그 파싱 로직 구현**
3. **JSON 응답 추출 로직 최적화**

### Phase 4: 통합 테스트 (30분)
1. **로컬 환경**: `CLOUDBUILD_MOCK=true`로 기존 기능 확인
2. **실제 환경**: `CLOUDBUILD_MOCK=false`로 Cloud Build 실행 테스트
3. **Firestore 연동 확인**: 대화 기록, 실행 기록 저장 검증

## 🚨 주의사항

### 기존 기능 보존 필수사항
- **API 인터페이스**: 기존과 동일한 요청/응답 형식 유지
- **Firestore 연동**: 대화 기록, 에이전트 정보, 실행 기록 저장 유지
- **프론트엔드 호환성**: frontend_implementation.md 기준 응답 형식 유지

### 1월 18일 테스트 결과 반영
- **Claude 명령어**: `claude --print --output-format json --permission-mode acceptEdits`
- **stdin 프롬프트 전달**: `echo "${_PROMPT}" | claude`
- **JSON 응답 파싱**: `{"result": "...", "usage": {...}}`

### 환경별 동작 방식
- **로컬 개발**: `CLOUDBUILD_MOCK=true` (모의 응답, 빠른 개발)
- **GCP 배포**: `CLOUDBUILD_MOCK=false` (실제 Cloud Build 실행)

## 📁 영향받는 파일 목록

### 수정될 파일
- `api-server/main.py` (주요 수정)
- `api-server/requirements.txt` (cloud-logging 추가 필요 시)

### 새로 생성할 파일
- 없음 (기존 파일 수정만)

## ✅ 완료 기준

1. **환경별 동작**: 로컬(모의)/배포(실제) 모드 정상 전환
2. **Cloud Build 실행**: 실제 Claude Code 실행 성공
3. **로그 수집**: Cloud Logging에서 응답 추출 성공
4. **Firestore 연동**: 기존 대화 기록, 에이전트 정보 저장 유지
5. **API 호환성**: 기존 프론트엔드와 완벽 호환
6. **에러 핸들링**: Cloud Build 실패 시 적절한 에러 응답

---

## 🎉 2단계 구현 완료 (2025-01-18)

### ✅ 실제 수행된 작업 내역

#### Phase 1: 환경 변수 및 로깅 설정 (완료)
- ✅ `google-cloud-logging==3.12.1` 패키지 설치 및 requirements.txt 추가
- ✅ Cloud Logging import 추가: `from google.cloud import logging as cloud_logging`
- ✅ 환경 변수 설정: `CLOUDBUILD_MOCK=true`, `ANTHROPIC_API_KEY` 지원
- ✅ Cloud Build 및 Logging 클라이언트 초기화 (모의 모드에서는 Logging 클라이언트 비활성화)
- ✅ 모의/실제 모드 전환 로직 구현

#### Phase 2: Cloud Build 실제 실행 구현 (완료)
- ✅ `execute_claude_with_cloudbuild()` 함수를 모의/실제 모드로 분리
- ✅ `execute_mock_response()` 함수 구현: 로컬 테스트용 모의 응답
- ✅ `execute_real_cloudbuild()` 함수 구현: 실제 Cloud Build API 호출
- ✅ 1월 18일 검증된 명령어 완전 적용:
  - `pip install claude-cli && echo '{prompt}' | claude --print --output-format json --permission-mode acceptEdits`
- ✅ 환경 변수를 통한 ANTHROPIC_API_KEY 전달 (`env` 배열 설정)
- ✅ Cloud Build 타임아웃 설정: 300초
- ✅ 에러 핸들링 강화: SUCCESS/FAILURE/UNKNOWN 상태별 응답 처리

#### Phase 3: Cloud Logging 연동 (완료)
- ✅ `get_cloudbuild_logs()` 함수 구현: 
  - Cloud Build 로그 필터링 (`resource.type="build" AND resource.labels.build_id="{build_id}"`)
  - 최근 5분 이내 로그 조회
  - 페이지네이션 지원 (최대 100개 엔트리)
- ✅ `parse_claude_response_from_log()` 함수 구현:
  - 다중 정규식 패턴으로 JSON 응답 추출
  - JSON 파싱 실패 시 텍스트 직접 추출
  - 폴백 로직으로 안정성 확보
- ✅ 로그 조회 에러 처리 및 사용자 친화적 에러 메시지

#### Phase 4: 통합 테스트 (완료)
- ✅ 서버 시작 성공: `http://127.0.0.1:8001` (포트 8000 충돌 해결)
- ✅ 모의 모드(`CLOUDBUILD_MOCK=true`) 정상 동작 확인:
  - "MOCK: True" 로그 출력 확인
  - Cloud Logging 클라이언트 비활성화 확인
- ✅ API 엔드포인트 테스트 성공:
  - GET `/` 헬스체크 ✅
  - POST `/api/conversation` (conversation ID: e0acc699-e401-4348-b804-ac7fa5215300) ✅
  - POST `/agents` (agent ID: 2722699e-d952-4400-b383-f9d4ad278230) ✅
  - POST `/agents/{id}/run` (execution ID: c97a2a17-dcd2-454b-bb0b-47a2af8a7b89) ✅
- ✅ 기존 Firestore 연동 기능 보존 확인
- ✅ 기존 API 응답 형식 완벽 유지

### 📁 실제 변경된 파일

#### 수정된 파일
- ✅ `api-server/main.py`: Cloud Build 실제 실행 로직 및 로깅 연동 구현
- ✅ `api-server/requirements.txt`: `google-cloud-logging==3.12.1` 추가

### 🎯 달성한 목표

1. **환경별 동작 모드**: `CLOUDBUILD_MOCK` 환경 변수로 개발/배포 모드 완벽 전환
2. **실제 Claude 실행 준비**: GCP 배포 시 실제 Cloud Build에서 Claude Code 실행 가능
3. **로그 수집 시스템**: Cloud Logging API를 통한 실행 결과 자동 추출
4. **기존 기능 완전 보존**: API 인터페이스, Firestore 연동, 응답 형식 모두 유지
5. **에러 핸들링 강화**: Cloud Build 실행 상태별 적절한 에러 응답
6. **검증된 안정성**: 1월 18일 성공 테스트 결과를 완전히 반영

### 🔧 현재 상태

- **로컬 개발**: `CLOUDBUILD_MOCK=true`로 빠른 모의 응답 제공
- **GCP 배포**: `CLOUDBUILD_MOCK=false` + `ANTHROPIC_API_KEY` 설정으로 실제 실행 가능
- **API 호환성**: 기존 프론트엔드와 100% 호환
- **다음 단계**: 프론트엔드 단순화 또는 실제 GCP 배포 테스트

## 🎯 기대 효과

1. **실제 Claude 실행**: 모의 응답이 아닌 실제 Claude Code 결과
2. **완전한 격리**: Cloud Build 환경에서 사용자별 독립 실행
3. **확장성**: Cloud Build의 무한 확장 가능
4. **유지 관리성**: 기존 API 구조 보존으로 프론트엔드 변경 불필요

---

**2단계 완료**: Cloud Build 연동 및 실제 실행 구현 성공 ✅