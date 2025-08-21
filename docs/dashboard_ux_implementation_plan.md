# AI 에이전트 플랫폼 - 대시보드 중심 UX 구현안

**작성일**: 2025년 8월 19일  
**상태**: 설계 단계  
**목표**: 에이전트 관리 중심의 직관적인 사용자 경험 구현

---

## 📋 개요

### 🎯 핵심 개선사항
현재의 단일 채팅 인터페이스에서 **에이전트 관리 대시보드 중심**의 사용자 경험으로 전환하여, 사용자가 여러 에이전트를 효율적으로 관리하고 작업할 수 있는 환경을 제공합니다.

### 🌟 새로운 사용자 플로우
```
메인 대시보드 → 에이전트 선택/생성 → 워크스페이스 → 에이전트 완성 → 대시보드 복귀
     ↓              ↓                ↓              ↓              ↓
   에이전트 목록    Docker 할당     Claude 대화    에이전트 저장   관리 및 실행
```

---

## 🏗️ 새로운 아키텍처 설계

### 📱 페이지 구조

#### 1. **메인 대시보드** (`/`)
- **에이전트 목록 표시**: 카드 기반 그리드 레이아웃
- **상태 표시**: 작업 중, 완료, 실행 중, 오류 등
- **빠른 액션**: 편집, 실행, 복제, 삭제
- **새 에이전트 생성 버튼**: 큰 CTA 버튼

#### 2. **에이전트 워크스페이스** (`/workspace/{agent_id}`)
- **기존 채팅 인터페이스 활용**: 현재 구현된 Claude 대화 시스템
- **에이전트 컨텍스트 로드**: 기존 대화 이력 및 설정 복원
- **진행 상태 저장**: 실시간 자동 저장

#### 3. **에이전트 상세 관리** (`/agent/{agent_id}`)
- **메타데이터 관리**: 이름, 설명, 태그, 스케줄
- **실행 로그 확인**: 과거 실행 기록 및 결과
- **설정 관리**: 권한, 리소스 제한 등

### 🗃️ 데이터 구조 (Firestore)

```javascript
// 에이전트 컬렉션
agents: {
  [agentId]: {
    // 기본 정보
    name: "주간 주식 분석 에이전트",
    description: "알파벳 관련 뉴스 수집 및 분석",
    status: "draft" | "active" | "paused" | "error",
    
    // 메타데이터
    userId: "user-id",
    createdAt: timestamp,
    updatedAt: timestamp,
    lastAccessedAt: timestamp,
    
    // 에이전트 설정
    finalPrompt: "자연어 에이전트 스크립트",
    schedule: {
      enabled: true,
      frequency: "weekly",
      dayOfWeek: 1, // 월요일
      time: "08:00"
    },
    
    // 실행 통계
    totalRuns: 5,
    successfulRuns: 4,
    lastRunAt: timestamp,
    avgExecutionTime: 120, // 초
    totalTokenUsage: { input: 15000, output: 25000 },
    
    // UI 상태
    tags: ["news", "stock", "analysis"],
    color: "#3B82F6", // 사용자 지정 색상
    icon: "📊" // 이모지 아이콘
  }
}

// 워크스페이스 세션 컬렉션
workspaces: {
  [sessionId]: {
    agentId: "agent-id",
    userId: "user-id",
    containerId: "docker-container-id",
    status: "active" | "idle" | "terminated",
    createdAt: timestamp,
    lastActivityAt: timestamp,
    
    // 대화 이력 (기존 구조 유지)
    messages: [...],
    
    // 워크스페이스 상태
    currentStep: "planning" | "testing" | "finalizing",
    progress: 0.7, // 0-1 범위
    autoSave: true
  }
}

// 실행 기록 컬렉션
executions: {
  [executionId]: {
    agentId: "agent-id",
    triggerType: "manual" | "scheduled",
    startTime: timestamp,
    endTime: timestamp,
    status: "success" | "failed" | "timeout",
    
    // 실행 결과
    result: {
      output: "실행 결과 데이터",
      files: ["path/to/generated/file1.csv"],
      logs: "실행 로그",
      error: "오류 메시지 (실패시)"
    },
    
    // 리소스 사용량
    resources: {
      tokenUsage: { input: 1234, output: 2567 },
      executionTime: 145, // 초
      memoryUsage: 512, // MB
      cpuUsage: 0.8 // 코어
    }
  }
}
```

---

## 🎨 UI/UX 설계

### 📊 메인 대시보드 레이아웃

```html
<!DOCTYPE html>
<html>
<head>
    <title>AI 에이전트 대시보드</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body>
    <!-- 헤더 -->
    <header class="bg-white shadow-sm border-b">
        <div class="flex justify-between items-center px-6 py-4">
            <h1 class="text-2xl font-bold text-gray-900">AI 에이전트 대시보드</h1>
            <div class="flex items-center space-x-4">
                <span id="user-info">guest-user-123</span>
                <button class="btn-primary">새 에이전트 만들기</button>
            </div>
        </div>
    </header>

    <!-- 메인 콘텐츠 -->
    <main class="container mx-auto px-6 py-8">
        
        <!-- 요약 통계 -->
        <section class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div class="stat-card">
                <h3>총 에이전트</h3>
                <span class="stat-number">12</span>
            </div>
            <div class="stat-card">
                <h3>활성 에이전트</h3>
                <span class="stat-number">8</span>
            </div>
            <div class="stat-card">
                <h3>이번 달 실행</h3>
                <span class="stat-number">156</span>
            </div>
            <div class="stat-card">
                <h3>성공률</h3>
                <span class="stat-number">94%</span>
            </div>
        </section>

        <!-- 에이전트 그리드 -->
        <section>
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-xl font-semibold">내 에이전트</h2>
                <div class="flex space-x-3">
                    <select class="filter-select">
                        <option>모든 상태</option>
                        <option>활성</option>
                        <option>초안</option>
                        <option>일시정지</option>
                    </select>
                    <input type="search" placeholder="에이전트 검색..." class="search-input">
                </div>
            </div>

            <!-- 에이전트 카드 그리드 -->
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                
                <!-- 새 에이전트 생성 카드 -->
                <div class="create-agent-card" onclick="createNewAgent()">
                    <div class="create-icon">+</div>
                    <h3>새 에이전트 만들기</h3>
                    <p>Claude와 대화하여 새로운 AI 에이전트를 설계하세요</p>
                </div>

                <!-- 기존 에이전트 카드들 -->
                <div class="agent-card" data-agent-id="agent-1">
                    <div class="agent-header">
                        <span class="agent-icon">📊</span>
                        <div class="agent-status status-active"></div>
                    </div>
                    
                    <h3 class="agent-name">주간 주식 분석</h3>
                    <p class="agent-description">알파벳 관련 뉴스 수집 및 분석</p>
                    
                    <div class="agent-stats">
                        <span>실행 5회</span>
                        <span>성공률 80%</span>
                        <span>2일 전</span>
                    </div>
                    
                    <div class="agent-actions">
                        <button onclick="editAgent('agent-1')">편집</button>
                        <button onclick="runAgent('agent-1')">실행</button>
                        <button onclick="viewAgent('agent-1')">상세</button>
                    </div>
                </div>

                <!-- 더 많은 에이전트 카드들... -->
            </div>
        </section>
    </main>
</body>
</html>
```

### 🎭 상태별 UI 표시

#### 에이전트 상태 아이콘
```css
.status-draft { background: #94A3B8; } /* 회색 - 초안 */
.status-active { background: #10B981; } /* 초록 - 활성 */
.status-running { background: #3B82F6; animation: pulse; } /* 파란색 깜빡임 - 실행 중 */
.status-paused { background: #F59E0B; } /* 노랑 - 일시정지 */
.status-error { background: #EF4444; } /* 빨강 - 오류 */
```

#### 진행 상황 표시
```javascript
// 워크스페이스에서 진행 상황 표시
const progressSteps = [
    { key: 'planning', label: '에이전트 기획', icon: '💭' },
    { key: 'development', label: '개발 중', icon: '⚙️' },
    { key: 'testing', label: '테스트', icon: '🧪' },
    { key: 'finalizing', label: '완성', icon: '✅' }
];

function updateProgress(currentStep, progress) {
    // 진행 상황 바 업데이트
    document.getElementById('progress-bar').style.width = `${progress * 100}%`;
    
    // 현재 단계 표시
    document.getElementById('current-step').textContent = 
        progressSteps.find(s => s.key === currentStep).label;
}
```

---

## 🔧 백엔드 API 확장

### 🛤️ 새로운 API 엔드포인트

#### 대시보드 API
```python
# 에이전트 관리 API
@app.get("/api/agents")
async def list_agents(user_id: str = Header(..., alias="X-User-Id")):
    """사용자의 모든 에이전트 목록 조회"""
    
@app.post("/api/agents")
async def create_agent(agent_data: AgentCreateRequest, user_id: str = Header(...)):
    """새 에이전트 생성 및 워크스페이스 할당"""
    
@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str, user_id: str = Header(...)):
    """특정 에이전트 상세 정보 조회"""
    
@app.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, agent_data: AgentUpdateRequest):
    """에이전트 정보 업데이트"""
    
@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, user_id: str = Header(...)):
    """에이전트 삭제 (컨테이너 및 데이터 정리)"""

# 워크스페이스 관리 API
@app.post("/api/agents/{agent_id}/workspace")
async def create_workspace(agent_id: str, user_id: str = Header(...)):
    """에이전트를 위한 워크스페이스 생성"""
    
@app.get("/api/workspace/{session_id}/restore")
async def restore_workspace(session_id: str):
    """기존 워크스페이스 상태 복원"""

# 실행 관리 API  
@app.post("/api/agents/{agent_id}/execute")
async def execute_agent(agent_id: str, manual: bool = True):
    """에이전트 수동 실행"""
    
@app.get("/api/agents/{agent_id}/executions")
async def get_execution_history(agent_id: str):
    """에이전트 실행 기록 조회"""

# 통계 API
@app.get("/api/dashboard/stats")
async def get_dashboard_stats(user_id: str = Header(...)):
    """대시보드 요약 통계"""
```

#### 데이터 모델
```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class AgentCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    tags: List[str] = []
    color: Optional[str] = "#3B82F6"
    icon: Optional[str] = "🤖"

class AgentUpdateRequest(BaseModel):
    name: Optional[str]
    description: Optional[str]
    status: Optional[str]
    finalPrompt: Optional[str]
    schedule: Optional[dict]
    tags: Optional[List[str]]
    color: Optional[str]
    icon: Optional[str]

class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    status: str
    userId: str
    createdAt: datetime
    updatedAt: datetime
    lastAccessedAt: Optional[datetime]
    totalRuns: int
    successfulRuns: int
    lastRunAt: Optional[datetime]
    tags: List[str]
    color: str
    icon: str

class WorkspaceCreateResponse(BaseModel):
    sessionId: str
    agentId: str
    containerId: str
    wsUrl: str  # WebSocket URL
    status: str
```

---

## 🔄 사용자 플로우 구현

### 📝 시나리오 1: 새 에이전트 생성

```javascript
// 1. 대시보드에서 "새 에이전트 만들기" 클릭
async function createNewAgent() {
    try {
        // 새 에이전트 생성
        const response = await fetch('/api/agents', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-User-Id': getCurrentUserId()
            },
            body: JSON.stringify({
                name: "새 에이전트",
                description: "",
                tags: [],
                color: "#3B82F6",
                icon: "🤖"
            })
        });
        
        const agent = await response.json();
        
        // 워크스페이스 생성 및 이동
        const workspace = await createWorkspace(agent.id);
        window.location.href = `/workspace/${workspace.sessionId}`;
        
    } catch (error) {
        console.error('에이전트 생성 실패:', error);
        showErrorMessage('에이전트를 생성할 수 없습니다.');
    }
}

// 2. 워크스페이스 생성
async function createWorkspace(agentId) {
    const response = await fetch(`/api/agents/${agentId}/workspace`, {
        method: 'POST',
        headers: {
            'X-User-Id': getCurrentUserId()
        }
    });
    
    return await response.json();
}
```

### ✏️ 시나리오 2: 기존 에이전트 편집

```javascript
// 1. 대시보드에서 에이전트 카드의 "편집" 버튼 클릭
async function editAgent(agentId) {
    try {
        // 기존 워크스페이스 확인
        const existingWorkspace = await checkExistingWorkspace(agentId);
        
        if (existingWorkspace) {
            // 기존 워크스페이스 복원
            window.location.href = `/workspace/${existingWorkspace.sessionId}`;
        } else {
            // 새 워크스페이스 생성
            const workspace = await createWorkspace(agentId);
            window.location.href = `/workspace/${workspace.sessionId}`;
        }
        
    } catch (error) {
        console.error('워크스페이스 생성 실패:', error);
    }
}

// 2. 워크스페이스 상태 복원
async function restoreWorkspaceState(sessionId) {
    const response = await fetch(`/api/workspace/${sessionId}/restore`);
    const workspace = await response.json();
    
    // 기존 대화 이력 로드
    loadChatHistory(workspace.messages);
    
    // 에이전트 정보 로드
    loadAgentContext(workspace.agentId);
    
    // 진행 상황 표시
    updateProgress(workspace.currentStep, workspace.progress);
}
```

---

## 💾 데이터 동기화 전략

### 🔄 실시간 상태 동기화

```javascript
// WebSocket을 통한 실시간 업데이트
class WorkspaceManager {
    constructor(sessionId, agentId) {
        this.sessionId = sessionId;
        this.agentId = agentId;
        this.autoSaveInterval = 30000; // 30초마다 자동 저장
        
        this.setupAutoSave();
        this.setupBeforeUnload();
    }
    
    // 자동 저장 설정
    setupAutoSave() {
        setInterval(async () => {
            await this.saveWorkspaceState();
        }, this.autoSaveInterval);
    }
    
    // 워크스페이스 상태 저장
    async saveWorkspaceState() {
        const state = {
            messages: this.getChatHistory(),
            currentStep: this.getCurrentStep(),
            progress: this.getProgress(),
            lastActivityAt: new Date().toISOString()
        };
        
        await fetch(`/api/workspace/${this.sessionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state)
        });
    }
    
    // 페이지 떠날 때 상태 저장
    setupBeforeUnload() {
        window.addEventListener('beforeunload', () => {
            // 동기 저장 (페이지 언로드 직전)
            navigator.sendBeacon(`/api/workspace/${this.sessionId}/sync`, 
                JSON.stringify(this.getWorkspaceState()));
        });
    }
}
```

### 📊 에이전트 메트릭 업데이트

```python
# 백엔드에서 에이전트 메트릭 자동 업데이트
class AgentMetricsManager:
    async def update_agent_activity(self, agent_id: str):
        """에이전트 활동 메트릭 업데이트"""
        
        agent_ref = db.collection('agents').document(agent_id)
        
        await agent_ref.update({
            'lastAccessedAt': datetime.utcnow(),
            'updatedAt': datetime.utcnow()
        })
    
    async def record_execution_result(self, agent_id: str, execution_result: dict):
        """실행 결과 기록 및 통계 업데이트"""
        
        # 실행 기록 저장
        execution_ref = db.collection('executions').document()
        await execution_ref.set({
            'agentId': agent_id,
            'result': execution_result,
            'createdAt': datetime.utcnow()
        })
        
        # 에이전트 통계 업데이트
        agent_ref = db.collection('agents').document(agent_id)
        
        if execution_result['status'] == 'success':
            await agent_ref.update({
                'totalRuns': firestore.Increment(1),
                'successfulRuns': firestore.Increment(1),
                'lastRunAt': datetime.utcnow()
            })
        else:
            await agent_ref.update({
                'totalRuns': firestore.Increment(1),
                'lastRunAt': datetime.utcnow()
            })
```

---

## 🎯 구현 우선순위

### Phase 1: 기본 대시보드 (1주)
- ✅ **메인 대시보드 페이지** 구현
- ✅ **에이전트 CRUD API** 개발
- ✅ **새 에이전트 생성 플로우** 구현
- ✅ **기본 에이전트 카드** UI

### Phase 2: 워크스페이스 통합 (1주)
- ✅ **기존 채팅 인터페이스** 워크스페이스로 전환
- ✅ **에이전트 컨텍스트 로드** 기능
- ✅ **자동 저장 시스템** 구현
- ✅ **진행 상황 추적** UI

### Phase 3: 고급 기능 (2주)
- ✅ **실행 이력 및 로그** 조회
- ✅ **에이전트 상태 관리** (일시정지, 활성화)
- ✅ **검색 및 필터링** 기능
- ✅ **에이전트 복제** 기능

### Phase 4: 최적화 (1주)
- ✅ **성능 최적화** (지연 로딩, 캐싱)
- ✅ **반응형 디자인** 완성
- ✅ **에러 처리** 강화
- ✅ **사용자 피드백** UI

---

## 🔍 기술적 고려사항

### 🐳 컨테이너 관리 최적화

```python
class OptimizedContainerManager:
    def __init__(self):
        self.container_pool = {}  # 재사용 가능한 컨테이너 풀
        self.warmup_containers = 3  # 미리 준비할 컨테이너 수
    
    async def get_or_create_workspace_container(self, agent_id: str, user_id: str):
        """에이전트별 최적화된 컨테이너 할당"""
        
        # 기존 컨테이너가 있는지 확인
        existing_container = await self.find_existing_container(agent_id)
        if existing_container and existing_container.status == 'running':
            return existing_container
        
        # 풀에서 미리 준비된 컨테이너 사용
        if self.container_pool:
            container = self.container_pool.pop()
            await self.configure_container_for_agent(container, agent_id)
            return container
        
        # 새 컨테이너 생성
        return await self.create_new_container(agent_id, user_id)
    
    async def warmup_container_pool(self):
        """컨테이너 풀 미리 준비 (백그라운드 작업)"""
        while len(self.container_pool) < self.warmup_containers:
            container = await self.create_base_container()
            self.container_pool.append(container)
```

### 📱 반응형 디자인

```css
/* 에이전트 카드 반응형 그리드 */
.agent-grid {
    display: grid;
    gap: 1.5rem;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
}

/* 모바일 최적화 */
@media (max-width: 768px) {
    .agent-grid {
        grid-template-columns: 1fr;
        gap: 1rem;
    }
    
    .agent-card {
        padding: 1rem;
    }
    
    .agent-actions {
        flex-direction: column;
        gap: 0.5rem;
    }
}

/* 태블릿 최적화 */
@media (min-width: 769px) and (max-width: 1024px) {
    .agent-grid {
        grid-template-columns: repeat(2, 1fr);
    }
}
```

---

## 📊 성능 및 확장성

### ⚡ 로딩 최적화 전략

```javascript
// 지연 로딩으로 성능 개선
class LazyDashboard {
    constructor() {
        this.loadedAgents = new Set();
        this.observerOptions = {
            root: null,
            rootMargin: '50px',
            threshold: 0.1
        };
        
        this.setupIntersectionObserver();
    }
    
    setupIntersectionObserver() {
        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this.loadAgentDetails(entry.target.dataset.agentId);
                }
            });
        }, this.observerOptions);
    }
    
    async loadAgentDetails(agentId) {
        if (this.loadedAgents.has(agentId)) return;
        
        try {
            const response = await fetch(`/api/agents/${agentId}`);
            const agent = await response.json();
            
            this.updateAgentCard(agentId, agent);
            this.loadedAgents.add(agentId);
            
        } catch (error) {
            console.error(`Failed to load agent ${agentId}:`, error);
        }
    }
}
```

### 🗄️ 캐싱 전략

```python
from functools import lru_cache
import redis
import json

class DashboardCache:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.cache_ttl = 300  # 5분
    
    async def get_user_dashboard_data(self, user_id: str):
        """사용자 대시보드 데이터 캐싱"""
        
        cache_key = f"dashboard:{user_id}"
        cached_data = self.redis_client.get(cache_key)
        
        if cached_data:
            return json.loads(cached_data)
        
        # 캐시 미스시 DB에서 로드
        dashboard_data = await self.load_dashboard_from_db(user_id)
        
        # 캐시에 저장
        self.redis_client.setex(
            cache_key, 
            self.cache_ttl, 
            json.dumps(dashboard_data, default=str)
        )
        
        return dashboard_data
    
    async def invalidate_user_cache(self, user_id: str):
        """사용자 캐시 무효화 (에이전트 변경시)"""
        cache_key = f"dashboard:{user_id}"
        self.redis_client.delete(cache_key)
```

---

## 🎉 결론

### ✨ 예상 효과

1. **사용자 경험 개선**
   - 에이전트 관리 중심의 직관적인 인터페이스
   - 작업 상태 및 진행 상황 명확한 추적
   - 여러 에이전트 병렬 작업 가능

2. **개발 효율성**
   - 기존 WebSocket 인프라 재활용
   - 점진적 기능 확장 가능
   - 모듈화된 구조로 유지보수 용이

3. **확장 가능성**
   - 에이전트 마켓플레이스 기반 마련
   - 팀 협업 기능 추가 용이
   - 자동화 및 스케줄링 시스템 통합 준비

### 🚀 다음 단계

1. **즉시 시작**: Phase 1 구현 (기본 대시보드)
2. **기능 검증**: 사용자 테스트 및 피드백 수집
3. **점진적 확장**: Phase 2-4 단계적 구현
4. **성능 최적화**: 실제 사용량 기반 튜닝

이 구현안을 통해 현재의 단순한 채팅 인터페이스에서 **전문적인 AI 에이전트 관리 플랫폼**으로 발전시킬 수 있습니다.