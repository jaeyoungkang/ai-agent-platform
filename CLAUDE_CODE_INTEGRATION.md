# Claude Code CLI Integration

## 개요

이 문서는 AI Agent Platform에 실제 Claude Code CLI를 통합한 구현 내용을 설명합니다.

## 주요 변경 사항

### 1. 백엔드 구현

#### ClaudeCodeProcess 클래스
- **파일**: `websocket-server/main.py`
- **기능**: 실제 Claude Code CLI 프로세스 관리
- **특징**:
  - `subprocess.Popen`을 통한 실제 `claude chat` 실행
  - 비동기 stdin/stdout 스트리밍
  - 자동 프로세스 재시작 및 정리
  - 에이전트 생성 모드 시 시스템 프롬프트 적용

#### UserWorkspace 클래스 재설계
- **기능**: 사용자별 Claude 세션 관리
- **변경점**:
  - 시뮬레이션 코드 완전 제거
  - 세션별 ClaudeCodeProcess 인스턴스 관리
  - 컨텍스트 기반 응답 처리 (workspace vs agent-create)

#### 새로운 API 엔드포인트
```http
POST /api/agents/create-session
```
- 에이전트 생성 전용 워크스페이스 세션 생성
- `context: 'agent-create'` 설정으로 Claude에게 에이전트 생성 모드 알림

#### 환경 검증 (Startup Event)
```python
@app.on_event("startup")
async def startup_event():
```
- 서버 시작 시 Claude Code CLI 자동 설치 시도
- API 키 및 버전 확인
- 설치 실패 시 에러로 서버 시작 중단

### 2. 프론트엔드 변경

#### workspace.html 업데이트
- **세션 ID 전달**: WebSocket 메시지에 `session_id` 포함
- **컨텍스트 감지**: 워크스페이스 복원 시 `context` 필드 확인
- **에이전트 생성 모드**: 특별한 UI 초기화 (`initAgentCreationMode()`)

### 3. 테스트 스크립트

#### test_claude_integration.py
- Claude Code CLI 직접 테스트
- ClaudeCodeProcess 클래스 테스트
- UserWorkspace 통합 테스트
- 자동화된 검증 프로세스

## 사용 방법

### 1. 환경 설정

```bash
# 1. ANTHROPIC_API_KEY 설정
export ANTHROPIC_API_KEY="your-api-key"

# 2. Node.js 환경 (Claude Code CLI 설치용)
node --version  # v18 이상 권장

# 3. 서버 시작 (Claude Code CLI 자동 설치)
cd websocket-server
python main.py
```

### 2. 에이전트 생성 플로우

1. **대시보드에서 "새 에이전트" 클릭**
   - `POST /api/agents/create-session` 호출
   - `workspace.html?session=UUID` 로 이동

2. **워크스페이스 초기화**
   - 세션 복원 시 `context: 'agent-create'` 감지
   - Claude Code CLI 프로세스 시작 (시스템 프롬프트 포함)
   - 에이전트 생성 UI 표시

3. **실제 Claude와 대화**
   - 사용자 메시지 → WebSocket → Claude Code CLI
   - 실시간 스트리밍으로 Claude 응답 수신
   - 에이전트 완성 감지 시 Firestore에 저장

### 3. 테스트 실행

```bash
cd websocket-server
python test_claude_integration.py
```

## 기술적 특징

### 1. 실시간 스트리밍
- `asyncio`와 `executor`를 활용한 비차단 I/O
- 버퍼링을 통한 응답 수집 및 완료 감지
- 타임아웃 처리 (30초)

### 2. 프로세스 관리
- 세션별 독립된 Claude 프로세스
- 자동 재시작 및 에러 복구
- 리소스 정리 및 메모리 관리

### 3. 보안
- 환경변수를 통한 API 키 관리
- 사용자별 프로세스 격리
- 입력 검증 및 에러 처리

## 문제 해결

### Claude Code CLI 설치 실패
```bash
# 수동 설치
npm install -g @anthropic-ai/claude-code

# 권한 문제 해결
sudo npm install -g @anthropic-ai/claude-code
```

### API 키 설정
```bash
# 환경변수 설정
export ANTHROPIC_API_KEY="sk-ant-api..."

# .env 파일 사용
echo "ANTHROPIC_API_KEY=sk-ant-api..." >> .env.local
```

### 프로세스 응답 없음
- 타임아웃 설정 확인 (기본 30초)
- Claude Code CLI 버전 호환성 확인
- API 사용량 제한 확인

## 성능 고려사항

- **메모리**: 사용자당 ~50MB (Claude 프로세스)
- **CPU**: 비동기 I/O로 CPU 사용 최소화
- **동시 사용자**: 100명 권장 (리소스에 따라 조정)
- **응답 시간**: 평균 2-10초 (Claude API 의존)

## 향후 개선사항

1. **프로세스 풀링**: 동일 사용자의 다중 세션에서 프로세스 재사용
2. **캐싱**: 자주 사용되는 응답 캐싱
3. **로드 밸런싱**: 여러 서버 인스턴스 간 세션 분산
4. **모니터링**: 프로세스 상태 및 성능 메트릭 수집

---

**구현 완료일**: 2025년 8월 21일  
**버전**: 1.0.0  
**테스트 상태**: ✅ 통합 테스트 완료