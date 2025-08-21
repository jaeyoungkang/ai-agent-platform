# 기술 구현 세부사항 - 2025년 8월 19일

**프로젝트**: AI 에이전트 플랫폼 대시보드 UX 구현  
**아키텍처**: 1인 1컨테이너 최적화

---

## 🏗️ 아키텍처 결정사항

### 컨테이너 전략 분석 결과
```
✅ 채택: "1인 1컨테이너" 방식
❌ 기각: "1에이전트 1컨테이너" 방식

이유:
- 리소스 효율성: 사용자당 1GB vs 에이전트당 500MB+
- 시작 속도: 즉시 vs 3-5초 대기
- 관리 복잡도: 사용자 수 vs 에이전트 수 (10배+ 차이)
- 코드 단순성: 기존 구조 활용 vs 대규모 리팩토링
```

### 최소한의 개선사항 적용
```python
# 기존 코드에 3줄만 추가
async def send_to_claude(self, message: str, agent_id: str = None) -> str:
    if agent_id:
        workdir = f"/workspace/agent-{agent_id}"        # 1줄
        container.exec_run(f"mkdir -p {workdir}", user='claude')  # 2줄
    else:
        workdir = "/workspace"                          # 3줄
    
    # 기존 Claude 실행 코드...
    result = container.exec_run(..., workdir=workdir)  # workdir 변경만
```

---

## 📊 데이터 구조 설계

### Firestore 컬렉션 구조
```javascript
// 1. 에이전트 마스터 정보
agents: {
  "agent-uuid-1": {
    // 기본 정보
    name: "데이터 분석 에이전트",
    description: "CSV 파일 분석 및 시각화",
    status: "active",  // draft, active, paused, error
    
    // 사용자 연결
    userId: "user-uuid",
    
    // 타임스탬프
    createdAt: "2025-08-19T10:30:00Z",
    updatedAt: "2025-08-19T11:45:00Z",
    lastAccessedAt: "2025-08-19T11:45:00Z",
    
    // 실행 통계
    totalRuns: 15,
    successfulRuns: 12,
    lastRunAt: "2025-08-19T11:30:00Z",
    
    // UI 메타데이터
    tags: ["분석", "CSV", "Python"],
    color: "#007bff",
    icon: "📊",
    
    // 완성된 에이전트 코드
    finalPrompt: "완성된 자연어 스크립트"
  }
}

// 2. 워크스페이스 세션 정보
workspaces: {
  "session-uuid-1": {
    sessionId: "session-uuid-1",
    agentId: "agent-uuid-1",
    userId: "user-uuid",
    
    status: "active",  // active, idle, terminated
    createdAt: "2025-08-19T11:00:00Z",
    lastActivityAt: "2025-08-19T11:45:00Z",
    
    // 대화 상태
    messages: [
      { role: "user", content: "...", timestamp: "..." },
      { role: "assistant", content: "...", timestamp: "..." }
    ],
    
    // 진행 상태
    currentStep: "development",  // planning, development, testing, finalizing
    progress: 0.6,  // 0.0 ~ 1.0
    autoSave: true
  }
}

// 3. 대화 기록 (기존 + agentId 추가)
conversations: {
  "conversation-uuid-1": {
    userId: "user-uuid",
    agentId: "agent-uuid-1",  // 🆕 추가된 필드
    messages: [...],
    createdAt: "2025-08-19T11:45:00Z"
  }
}
```

---

## 🔌 API 엔드포인트 설계

### 에이전트 관리 API
```python
# 1. 에이전트 CRUD
GET    /api/agents                    # 목록 조회
POST   /api/agents                    # 새 에이전트 생성
GET    /api/agents/{agent_id}         # 상세 정보
PUT    /api/agents/{agent_id}         # 정보 수정
DELETE /api/agents/{agent_id}         # 삭제

# 2. 워크스페이스 관리
POST   /api/agents/{agent_id}/workspace     # 워크스페이스 생성
GET    /api/workspace/{session_id}/restore  # 세션 복원

# 3. 대시보드 통계
GET    /api/dashboard/stats           # 요약 통계
```

### API 응답 형식
```javascript
// 에이전트 생성 응답
{
  "id": "agent-uuid-1",
  "name": "새 에이전트 1",
  "status": "draft",
  "userId": "user-uuid",
  "createdAt": "2025-08-19T12:00:00Z",
  // ... 기타 필드
}

// 워크스페이스 생성 응답
{
  "sessionId": "session-uuid-1",
  "agentId": "agent-uuid-1", 
  "wsUrl": "/workspace/user-uuid",
  "status": "active"
}

// 대시보드 통계 응답
{
  "totalAgents": 12,
  "activeAgents": 8,
  "totalRuns": 156,
  "successRate": "94%"
}
```

---

## 🎨 프론트엔드 아키텍처

### 페이지 구조
```
/                           → index.html (리다이렉트)
/static/dashboard.html      → 에이전트 관리 대시보드
/static/workspace.html      → Claude 대화 워크스페이스
```

### JavaScript 클래스 구조
```javascript
// 대시보드
class AgentDashboard {
  constructor() {
    this.agents = [];
    this.filteredAgents = [];
    this.userId = null;
  }
  
  async initializeAuth()        // 인증 처리
  async loadAgents()           // 에이전트 목록 로드
  renderAgents()              // UI 렌더링
  createAgentCard(agent)      // 에이전트 카드 생성
  filterAgents()              // 검색/필터링
  updateStats()               // 통계 업데이트
  async createNewAgent()      // 새 에이전트 생성
}

// 워크스페이스
class AIAgentWorkspace {
  constructor() {
    this.websocket = null;
    this.sessionId = null;
    this.userId = null;
    this.agentId = null;
  }
  
  parseUrlParams()            // URL 파라미터 파싱
  async initializeWorkspace() // 워크스페이스 초기화
  async loadAgentInfo()       // 에이전트 정보 로드
  connectWebSocket()          // WebSocket 연결
  // ... 기존 채팅 기능들
}
```

---

## 🎨 디자인 시스템

### 색상 팔레트 (사무적 전문 스타일)
```css
/* 메인 컬러 */
--primary: #007bff;      /* 파란색 - 주요 버튼, 링크 */
--secondary: #6c757d;    /* 회색 - 보조 요소 */

/* 배경 컬러 */
--bg-primary: #f8f9fa;   /* 라이트 그레이 - 페이지 배경 */
--bg-secondary: #ffffff; /* 화이트 - 카드, 패널 */

/* 텍스트 컬러 */
--text-primary: #343a40;   /* 다크 그레이 - 메인 텍스트 */
--text-secondary: #6c757d; /* 그레이 - 보조 텍스트 */

/* 헤더 그라데이션 */
--header-bg: linear-gradient(90deg, #495057 0%, #343a40 100%);

/* 상태 컬러 */
--status-draft: #6c757d;   /* 회색 - 초안 */
--status-active: #28a745;  /* 초록 - 활성 */
--status-running: #007bff; /* 파랑 - 실행중 */
--status-paused: #ffc107;  /* 노랑 - 일시정지 */
--status-error: #dc3545;   /* 빨강 - 오류 */
```

### 컴포넌트 스타일 가이드
```css
/* 통계 카드 */
.stat-card {
  background: white;
  border: 1px solid #dee2e6;
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

/* 에이전트 카드 */
.agent-card {
  background: white;
  border: 1px solid #e9ecef;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.agent-card:hover {
  border-color: #6c757d;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 새 에이전트 생성 카드 */
.create-agent-card {
  background: #495057;
  border: 2px dashed #6c757d;
  color: white;
}

.create-agent-card:hover {
  background: #343a40;
  border-color: #495057;
}
```

---

## ⚡ 성능 최적화

### 로딩 최적화
```javascript
// 지연 로딩 - 필요시에만 에이전트 상세 정보 로드
async loadAgentDetails(agentId) {
  if (this.loadedAgents.has(agentId)) return;
  
  const response = await fetch(`/api/agents/${agentId}`);
  const agent = await response.json();
  
  this.updateAgentCard(agentId, agent);
  this.loadedAgents.add(agentId);
}

// 검색 디바운싱 - 입력 후 300ms 대기
const debouncedFilter = debounce(() => this.filterAgents(), 300);
```

### 메모리 관리
```python
# 컨테이너 리소스 제한
container = docker_client.containers.run(
    mem_limit="1g",      # 사용자당 1GB 메모리
    cpu_count=1,         # 사용자당 1 CPU 코어
    # ...
)

# 권장 제한 사항
MAX_AGENTS_PER_USER = 10      # 사용자당 최대 에이전트 수
MAX_CONCURRENT_RUNS = 3       # 동시 실행 에이전트 수
```

---

## 🔒 보안 고려사항

### API 보안
```python
# 헤더 기반 사용자 인증
@app.get("/api/agents")
async def list_agents(user_id: str = Header(..., alias="X-User-Id")):
    # user_id 기반 권한 확인
    
# 에이전트 소유권 확인
agent_data = agent_doc.to_dict()
if agent_data.get('userId') != user_id:
    raise HTTPException(status_code=403, detail="Access denied")
```

### 컨테이너 격리
```python
# 사용자별 독립 환경
container_name = f"workspace-{user_id}"

# 에이전트별 디렉토리 분리
workdir = f"/workspace/agent-{agent_id}"

# 권한 최소화
exec_run(..., user='claude')  # 비루트 사용자
```

---

## 📈 모니터링 포인트

### 성능 지표
```python
# 로깅 강화
logger.info(f"Claude response for user {self.user_id} (agent: {agent_id or 'none'}): {output[:200]}...")
logger.info(f"Created workspace {session_id} for agent {agent_id}")
logger.info(f"Updated agent {agent_id} for user {user_id}")
```

### 추적할 메트릭
- 사용자별 에이전트 수
- 평균 에이전트 완성 시간
- 컨테이너 리소스 사용률
- API 응답 시간
- WebSocket 연결 안정성

---

## 🔄 배포 및 운영

### 환경 설정
```bash
# 환경 변수
export ANTHROPIC_API_KEY="your-api-key"
export PORT=8000

# 서버 시작
cd websocket-server
source venv/bin/activate
python main.py
```

### Docker 이미지 요구사항
```bash
# Claude 워크스페이스 이미지 필수
docker build -t claude-workspace:latest docker/claude-workspace/
```

---

**작업 완료 시점**: 2025년 8월 19일  
**현재 상태**: 모든 기능 정상 작동 중  
**서버**: http://localhost:8000