# AI 에이전트 플랫폼 - 통합 문서

**프로젝트명**: Claude Code CLI 기반 AI 에이전트 플랫폼  
**개발 일자**: 2025년 8월 19일  
**최종 업데이트**: 2025년 8월 21일 (Phase 3: Claude Code CLI 실제 통합 완료)  
**상태**: ✅ 실제 Claude Code CLI 통합 완료 + 구글 인증 기반 전체 시스템 작동  
**아키텍처**: 실제 Claude Code 기반 에이전트 생성 시스템

---

## 📋 프로젝트 개요

### 🎯 핵심 비전
**"사용자는 개별 가상환경에서 Claude Code CLI와 Python 패키지를 이용하여 에이전트를 설계하고 구동한다"**

이 프로젝트는 **에이전트 운영을 위한 가상 환경**을 제공하는 서비스입니다, 사용자는 가상환경과 연결된 웹인터페이스를통해서 에이전트를 만들고 운용합니다.

### 🌟 핵심 가치 제안
1. **쉬운 인터페이스**: 쉬운 인터페이스
2. **1인 1컨테이너**: 1인 1컨테이너로 리소스 최적화
3. **에이전트별 격리**: 독립 작업 디렉토리 (`/workspace/agent-{id}`)
4. **실시간 상호작용**: WebSocket 기반 Claude Code 와 상호작용
5. **최적화된 웹 접근**: 루트 경로(/)에서 바로 접근 가능한 사용자 친화적 URL

---

## 🏗️ 시스템 아키텍처

### 💡 아키텍처 철학
**"최대한 단순하고 직관적으로 구성"**을 원칙으로, 복잡한 중간 레이어 없이 사용자가 Claude Code CLI와 직접 상호작용할 수 있도록 설계했습니다.

### 🔧 시스템 아키텍처
```
┌─────────────────┐    WebSocket    ┌──────────────────┐    Docker API    ┌─────────────────────┐
│   사용자 브라우저   │ ◄────────────►  │  FastAPI 서버     │ ◄──────────────► │  Docker 컨테이너      │
│   (Web UI)      │                 │  (중개자 역할)      │                  │  (Claude CLI +      │
└─────────────────┘                 └──────────────────┘                  │   Python 환경)       │
                                            │                             └─────────────────────┘
                                            ▼
                                    ┌──────────────────┐
                                    │ Cloud Firestore  │
                                    │ (데이터 저장소)     │
                                    └──────────────────┘
```

### 🎨 핵심 설계 원칙
1. **1인 1컨테이너**: 각 사용자에게 독립된 실행 환경 제공
2. **직접 통신**: 중간 변환 없이 Claude Code CLI와 직접 대화
3. **상태 없는 서버**: 모든 상태는 컨테이너와 Firestore에 저장
4. **최소 권한**: 컨테이너 내에서만 제한된 권한으로 실행
5. **자동 정리**: 세션 종료 시 자동 리소스 해제

### 🐳 컨테이너 관리 전략

#### 현재 패턴: "1인 1컨테이너" (최적화)
```
사용자 A → 컨테이너 A → 에이전트 1, 2, 3, 4...
사용자 B → 컨테이너 B → 에이전트 5, 6, 7...
사용자 C → 컨테이너 C → 에이전트 8, 9...
```

**장점:**
- ✅ 리소스 효율적: 에이전트마다 컨테이너를 만들지 않음
- ✅ 빠른 에이전트 생성: 컨테이너 재사용으로 즉시 시작
- ✅ 단순한 구조: 사용자당 하나의 환경
- ✅ 관리 용이: 사용자별 데이터 격리

#### 에이전트별 작업 디렉토리 분리
```python
# 최소한의 개선 (3줄 코드 추가)
async def send_to_claude(self, message: str, agent_id: str = None):
    if agent_id:
        workdir = f"/workspace/agent-{agent_id}"        # 1줄
        container.exec_run(f"mkdir -p {workdir}", user='claude')  # 2줄
    else:
        workdir = "/workspace"                          # 3줄
    
    # 기존 Claude 실행 코드...
    result = container.exec_run(..., workdir=workdir)
```

---

## 📦 기술 스택

### 📊 기술 구성
| 계층 | 기술 | 버전 | 역할 |
|------|------|------|------|
| **Frontend** | HTML5 + TailwindCSS + Vanilla JS | Latest | 사용자 인터페이스 |
| **Backend** | Python FastAPI | 0.115.6 | API 서버 및 WebSocket 처리 |
| **Real-time** | WebSocket | 14.1 | 실시간 사용자-컨테이너 통신 |
| **Container** | Docker | Latest | 사용자별 격리 환경 |
| **AI Engine** | Claude Code CLI | 1.0.84 | AI 에이전트 실행 엔진 |
| **Database** | Google Cloud Firestore | 2.20.0 | 대화 및 사용자 데이터 |

### 🐳 Docker 워크스페이스 구성
```dockerfile
FROM node:18-bullseye

# Claude Code CLI 설치
RUN npm install -g @anthropic-ai/claude-code

# Python 환경 구성
RUN apt-get update && apt-get install -y python3 python3-pip git curl bash

# 핵심 Python 패키지 사전 설치
RUN pip3 install pandas numpy requests beautifulsoup4 matplotlib seaborn \
                 jupyter scikit-learn plotly openpyxl python-dotenv

# 보안을 위한 비루트 사용자 생성
RUN useradd -m -s /bin/bash claude
USER claude
WORKDIR /workspace

# 컨테이너가 백그라운드에서 계속 실행되도록 설정
CMD ["tail", "-f", "/dev/null"]
```

---

## 🎨 사용자 경험 (UX) 설계

### 🌐 사용자 플로우
```
메인 대시보드 → 에이전트 선택/생성 → 워크스페이스 → 에이전트 완성 → 대시보드 복귀
     ↓              ↓                ↓              ↓              ↓
   에이전트 목록    Docker 할당     Claude 대화    에이전트 저장   관리 및 실행
```

### 📱 페이지 구조

#### 1. **메인 대시보드** (`/`)
```html
┌─────────────────────────────────────────┐
│ 🏢 에이전트 관리 시스템        [+ 새 에이전트] │
├─────────────────────────────────────────┤
│ 📊 통계                                 │
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐         │
│ │총 12│ │활성8│ │156회│ │94% │         │
│ └─────┘ └─────┘ └─────┘ └─────┘         │
├─────────────────────────────────────────┤
│ 🤖 내 에이전트               [검색] [필터] │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│ │[+]      │ │📄 데이터 │ │📊 주식   │     │
│ │새 에이전트│ │분석     │ │분석     │     │
│ │생성     │ │[편집][실행]│ │[편집][실행]│     │
│ └─────────┘ └─────────┘ └─────────┘     │
└─────────────────────────────────────────┘
```

#### 2. **에이전트 워크스페이스** (`/workspace/{session_id}`)
```html
┌─────────────────────────────────────────┐
│ 🏢 워크스페이스 - 데이터 분석 에이전트      │
├─────────────────────────────────────────┤
│ 💬 Claude와의 대화                       │
│                                         │
│ 👤 사용자: CSV 파일을 분석하는 스크립트를... │
│                                         │
│ 🤖 Claude: 물론입니다! CSV 파일 분석을...  │
│                                         │
├─────────────────────────────────────────┤
│ [메시지 입력창]                    [전송] │
└─────────────────────────────────────────┘
```

### 🎨 디자인 시스템 (전문적 사무 스타일)

#### 색상 팔레트
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

/* 상태 컬러 */
--status-draft: #6c757d;   /* 회색 - 초안 */
--status-active: #28a745;  /* 초록 - 활성 */
--status-running: #007bff; /* 파랑 - 실행중 */
--status-paused: #ffc107;  /* 노랑 - 일시정지 */
--status-error: #dc3545;   /* 빨강 - 오류 */
```

### 📖 에이전트 생성 예시 대화

### **상세 예시 대화: '주간 주식 뉴스 분석 에이전트' 생성 과정**

(새루운 세션 시작)
**사용자:**
> 안녕하세요. 매주 특정 주식에 대한 최신 정보를 수집하고 분석하는 에이전트를 만들고 싶어요.

**AI 어시스턴트:**
> 네, 좋습니다! '주간 주식 분석 에이전트' 생성을 시작하겠습니다. 먼저, 이 에이전트가 언제 실행되기를 원하시나요? 스케줄을 설정해주세요.

**사용자:**
> 매주 월요일 오전 8시에 자동으로 실행되었으면 합니다.

**AI 어시스턴트:**
> `[상태 표시: 스케줄 설정 중...]`
> 알겠습니다. 스케줄이 다음과 같이 설정되었습니다.
> `[UI 컴포넌트: 스케줄 정보]`
> **실행 주기:** 매주
> **실행 요일:** 월요일
> **실행 시간:** 오전 8:00
> 이제 에이전트가 수행할 첫 번째 작업을 알려주세요.

**사용자:**
> 첫 번째 작업은, 지난 1주일 동안 '알파벳(Alphabet)' 사와 관련된 주요 뉴스들을 중복 없이, 관련도 순으로 수집하는 것입니다.

**AI 어시스턴트:**
> `[상태 표시: 작업 분석 중...]`
> 네, 첫 번째 작업으로 '알파벳(Alphabet) 주간 뉴스 수집'을 설정하겠습니다. 이 작업을 위해 `Google News API`를 사용하는 것이 가장 효율적일 것 같습니다. 설정이 잘 되었는지 확인하기 위해, 지난 1주일간의 데이터를 바탕으로 테스트를 한번 실행해 보겠습니다.
> `[상태 표시: 테스트 실행 중...]`
> `[UI 컴포넌트: 테스트 결과 요약]`
> **테스트 요약:** 총 152개의 관련 뉴스를 발견했으며, 중복 및 광고성 기사를 제외하고 118개의 유효한 뉴스를 수집했습니다.
> **샘플 데이터:**
> 1. "Alphabet, AI 신규 모델 발표로 주가 상승" (Reuters)
> 2. "Waymo, 자율주행 서비스 지역 확대" (TechCrunch)
> 3. ...
> `[UI 컴포넌트: 토큰 사용량 정보]`
> **토큰 사용량:** 입력 1,234 토큰, 출력 2,567 토큰
> `[상세 결과 보기 버튼]`
> 이 결과가 만족스러우신가요? 다음 단계를 진행할까요?

**사용자:**
> 네, 아주 좋습니다. 그럼 다음 단계로, 수집된 118개의 뉴스 기사 본문을 3개의 핵심 문장으로 각각 요약해주세요.

**AI 어시스턴트:**
> `[상태 표시: 작업 분석 중...]`
> 알겠습니다. 두 번째 작업으로 '수집된 뉴스 3줄 요약'을 추가합니다. 요약 작업에는 최신 자연어 처리 모델을 사용하겠습니다.
> 이제 모든 단계가 설정되었습니다. 생성된 에이전트의 최종 작업 흐름은 다음과 같습니다.
> `[UI 컴포넌트: 에이전트 최종 정보]`
> **에이전트 이름:** 주간 주식 분석 에이전트
> **실행 스케줄:** 매주 월요일 오전 8:00
> **작업 흐름:**
> 1. **(뉴스 수집)** 지난 1주일간 '알파벳' 관련 뉴스를 관련도 순으로 수집
> 2. **(뉴스 요약)** 수집된 각 뉴스를 3개의 핵심 문장으로 요약
> `[UI 컴포넌트: 예상 토큰 사용량]`
> **예상 월간 사용량:** 입력 ~15,000 토큰, 출력 ~25,000 토큰
> 이대로 에이전트 생성을 완료할까요?

**사용자:**
> 완벽합니다. 생성해주세요.

**AI 어시스턴트:**
> `[상태 표시: 에이전트 생성 중...]`
> '주간 주식 분석 에이전트' 생성이 완료되었습니다! 이제 대시보드에서 에이전트의 상태를 확인하고 관리할 수 있습니다.
> `[UI 컴포넌트: 에이전트 카드 - 토큰 사용량 표시]`
> **생성 완료 - 주간 주식 분석 에이전트**
> • 현재 상태: 활성화됨
> • 누적 토큰 사용량: 입력 3,801 토큰, 출력 6,134 토큰
> • 다음 실행 예정: 2024년 1월 8일 월요일 오전 8:00

---

## 🔌 API 설계

### 🛤️ API 엔드포인트

#### 에이전트 관리 API
```python
# 에이전트 CRUD
GET    /api/agents                    # 목록 조회
POST   /api/agents                    # 새 에이전트 생성
GET    /api/agents/{agent_id}         # 상세 정보
PUT    /api/agents/{agent_id}         # 정보 수정
DELETE /api/agents/{agent_id}         # 삭제

# 워크스페이스 관리
POST   /api/agents/{agent_id}/workspace     # 워크스페이스 생성
GET    /api/workspace/{session_id}/restore  # 세션 복원

# 대시보드 통계
GET    /api/dashboard/stats           # 요약 통계

# 기존 WebSocket
WS     /workspace/{user_id}          # 사용자별 워크스페이스 연결
```

#### API 응답 형식
```javascript
// 에이전트 생성 응답
{
  "id": "agent-uuid-1",
  "name": "새 에이전트 1",
  "status": "draft",
  "userId": "user-uuid",
  "createdAt": "2025-08-19T12:00:00Z"
}

// 대시보드 통계 응답
{
  "totalAgents": 12,
  "activeAgents": 8,
  "totalRuns": 156,
  "successRate": "94%"
}
```

### 🗃️ 데이터 구조 (Firestore)

```javascript
// 에이전트 마스터 정보
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

// 워크스페이스 세션 정보
workspaces: {
  "session-uuid-1": {
    sessionId: "session-uuid-1",
    agentId: "agent-uuid-1",
    userId: "user-uuid",
    
    status: "active",  // active, idle, terminated
    createdAt: "2025-08-19T11:00:00Z",
    lastActivityAt: "2025-08-19T11:45:00Z",
    
    // 대화 상태
    messages: [...],
    
    // 진행 상태
    currentStep: "development",  // planning, development, testing, finalizing
    progress: 0.6,  // 0.0 ~ 1.0
    autoSave: true
  }
}

// 대화 기록 (기존 + agentId 추가)
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

## ⚡ 성능 및 확장성

### 📊 성능 메트릭
| 지표 | 측정값 | 목표값 | 상태 |
|------|--------|--------|------|
| **컨테이너 시작 시간** | 즉시 (재사용) | <10초 | ✅ 달성 |
| **WebSocket 연결 시간** | <1초 | <2초 | ✅ 달성 |
| **Claude 응답 시간** | 2-10초 | <15초 | ✅ 달성 |
| **메모리 사용량** | 1GB/컨테이너 | <2GB | ✅ 달성 |
| **동시 사용자** | 100명 (예상) | 100명 | 🟡 예상 |

### 🔧 리소스 제한 및 권장사항
```python
# 컨테이너 리소스 제한
container = docker_client.containers.run(
    mem_limit="1g",      # 사용자당 1GB 메모리
    cpu_count=1,         # 사용자당 1 CPU 코어
)

# 권장 제한 사항
MAX_AGENTS_PER_USER = 10      # 사용자당 최대 에이전트 수
MAX_CONCURRENT_RUNS = 3       # 동시 실행 에이전트 수
```

### ⚡ 성능 최적화

#### 지연 로딩 및 캐싱
```javascript
// 필요시에만 에이전트 상세 정보 로드
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

---

## 🔒 보안 및 격리

### 🛡️ 보안 계층
1. **컨테이너 격리**
   - 사용자별 완전 분리된 파일시스템
   - 메모리 1GB, CPU 1코어 제한
   - 네트워크 격리 (bridge 모드)

2. **권한 제어**
   - 비루트 사용자(claude)로 실행
   - `--dangerously-skip-permissions` 플래그 (컨테이너 내에서만 안전)
   - 파일시스템 접근 제한

3. **세션 관리**
   - 24시간 자동 만료
   - UUID 기반 세션 ID
   - 메모리 기반 세션 스토어

### 🔐 API 보안
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

---

## 🚀 배포 및 운영

### 🐳 로컬 개발 환경 설정
```bash
# 1. 저장소 클론
cd /Users/jaeyoungkang/workspace/ai-agent-platform

# 2. Python 가상환경 설정
cd websocket-server
source venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. Docker 이미지 빌드
docker build -t claude-workspace:latest ../docker/claude-workspace/

# 5. 환경변수 설정
export ANTHROPIC_API_KEY="your-api-key"

# 6. 서버 실행
python main.py

# 7. 브라우저에서 접속
open http://localhost:8000
```

### 📊 모니터링 포인트
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

## 📁 프로젝트 파일 구조

```
ai-agent-platform/
├── PROJECT_DOCUMENTATION.md         # 기존 전체 프로젝트 문서
├── CONSOLIDATED_DOCUMENTATION.md    # 🆕 통합 문서 (이 파일)
├── README.md                        # 프로젝트 소개
├── docker/claude-workspace/         # Docker 환경
│   └── Dockerfile
├── websocket-server/                # 메인 서버
│   ├── main.py                     # FastAPI 서버 + 에이전트 API
│   ├── auth.py                     # 인증 시스템
│   ├── static/
│   │   ├── index.html              # 리다이렉트 페이지
│   │   ├── dashboard.html          # 🆕 메인 대시보드
│   │   └── workspace.html          # 🆕 워크스페이스
│   └── venv/
└── _documents/                      # 개별 문서 (참고용)
    ├── 2025-08-19/                  # 당일 작업 내역
    ├── architecture_improvement_plan.md
    ├── architecture_analysis_update.md
    ├── dashboard_ux_implementation_plan.md
    └── ux_example.md
```

---

## 🧪 테스트 가이드

### 기본 플로우 테스트
```bash
# 1. 브라우저에서 http://localhost:8000 접속
# 2. 자동으로 대시보드로 리다이렉트 확인
# 3. "새 에이전트 생성" 클릭
# 4. 워크스페이스로 이동 확인
# 5. Claude와 대화 테스트
# 6. 대시보드로 돌아가기
```

### API 직접 테스트
```bash
# 헬스체크
curl http://localhost:8000/health

# 에이전트 목록 (빈 목록 반환 예상)
curl -H "X-User-Id: test-user" http://localhost:8000/api/agents

# 새 에이전트 생성
curl -X POST -H "Content-Type: application/json" -H "X-User-Id: test-user" \
     -d '{"name":"테스트 에이전트","description":"테스트용"}' \
     http://localhost:8000/api/agents

# 대시보드 통계
curl -H "X-User-Id: test-user" http://localhost:8000/api/dashboard/stats
```

---


**다음 마일스톤**: 🚀 **클라우드 배포 및 확장**

---

**문서 버전**: 2.0 (통합 버전)  
**최종 업데이트**: 2025년 8월 19일  
**상태**: ✅ **대시보드 UX 완성** + **문서 통합 완료**