# AI 에이전트 플랫폼 단순화 아키텍처

## 핵심 컨셉
**사용자는 개별 가상환경에서 Claude Code CLI와 Python 패키지를 이용하여 에이전트를 설계하고 구동한다**

## 단순화된 아키텍처

### 기본 원리
```
사용자 ↔ 웹 인터페이스 ↔ 개별 컨테이너 (Claude Code CLI + Python)
```

- **1인 1컨테이너**: 각 사용자는 독립된 가상환경 제공
- **직접 상호작용**: Claude Code CLI와 직접 대화
- **실시간 실행**: 패키지 설치부터 코드 실행까지 즉시 확인
- **완전한 격리**: 사용자간 환경 분리로 안전성 확보

### 사용자 경험
1. **로그인** → 개별 컨테이너 할당
2. **Claude와 대화** → 에이전트 설계 및 테스트
3. **실시간 확인** → 코드 작성, 패키지 설치, 실행 결과
4. **에이전트 완성** → 스케줄 설정으로 자동 실행

## 단순화된 구현 방안

### 핵심 API (단 하나)
```python
@app.websocket("/workspace/{user_id}")
async def user_workspace(websocket: WebSocket, user_id: str):
    """사용자 전용 워크스페이스 - 개별 컨테이너와 직접 연결"""
    
    # 1. 사용자 전용 컨테이너 할당
    container = await get_or_create_user_container(user_id)
    
    # 2. WebSocket을 통해 실시간 Claude 대화
    async for message in websocket.iter_text():
        # 사용자 메시지를 컨테이너의 Claude Code CLI로 직접 전달
        response = await execute_claude_in_container(container, message)
        await websocket.send_text(response)

async def get_or_create_user_container(user_id: str):
    """사용자별 영구 컨테이너 관리"""
    container_name = f"workspace-{user_id}"
    
    # 기존 컨테이너가 있으면 재사용
    if container_exists(container_name):
        return get_container(container_name)
    
    # 새 컨테이너 생성
    return await docker_client.containers.run(
        image="claude-workspace:latest",
        name=container_name,
        environment={"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY},
        network_mode="bridge",
        mem_limit="1g", cpu_count=1,
        detach=True,
        volumes={f"/data/{user_id}": {"bind": "/workspace", "mode": "rw"}}
    )
```

### 워크스페이스 이미지
```dockerfile
# claude-workspace:latest
FROM node:18-bullseye

# Claude Code CLI 설치
RUN npm install -g @anthropic-ai/claude-code

# Python 환경 설치
RUN apt-get update && apt-get install -y python3 python3-pip

# 기본 패키지 설치
RUN pip install pandas numpy requests beautifulsoup4 matplotlib seaborn

# 작업 환경 설정
RUN useradd -m -s /bin/bash claude
USER claude
WORKDIR /workspace

# Claude Code CLI가 바로 실행되도록 설정
CMD ["bash"]
```

### 프론트엔드 (극단적 단순화)
```html
<!-- 단일 페이지 -->
<div id="workspace">
    <div id="chat-area">
        <!-- Claude와 실시간 대화 -->
    </div>
    <input id="message-input" placeholder="Claude에게 메시지 입력...">
</div>

<script>
// WebSocket으로 사용자 컨테이너와 직접 연결
const ws = new WebSocket(`ws://localhost:8003/workspace/${userId}`);

ws.onmessage = (event) => {
    displayMessage('claude', event.data);
};

document.getElementById('message-input').onkeypress = (e) => {
    if (e.key === 'Enter') {
        const message = e.target.value;
        ws.send(message);
        displayMessage('user', message);
        e.target.value = '';
    }
};
</script>
```

## 단순화된 성능 지표

### 사용자 경험
| 상황 | 응답시간 | 기능 |
|------|----------|------|
| **로그인** | 5초 | 개별 컨테이너 할당 |
| **Claude 대화** | 2-10초 | 실시간 에이전트 설계 |
| **코드 실행** | 즉시 | 패키지 설치 + 실행 확인 |
| **에이전트 완성** | 즉시 | 스케줄 설정 |

### 확장성
- **동시 사용자**: 100명 (컨테이너당 1GB 메모리 기준)
- **컨테이너 수명**: 사용자 세션 동안 유지
- **리소스**: 필요 시 자동 확장

## 구현 단계 (극단적 단순화)

### 1주차: 핵심 기능 구현
1. **Docker 이미지 생성**: `claude-workspace:latest`
2. **WebSocket API 구현**: 사용자 ↔ 컨테이너 연결
3. **기본 웹 인터페이스**: 채팅창 하나

### 2주차: 사용자 관리
1. **컨테이너 생명주기 관리**: 생성/유지/삭제
2. **데이터 영속성**: 사용자별 작업 공간 저장
3. **기본 인증**: 사용자 구분

### 3주차: 스케줄링
1. **에이전트 저장**: 완성된 에이전트 등록
2. **백그라운드 실행**: 정해진 시간에 자동 실행
3. **결과 확인**: 실행 결과 조회

## 핵심 구현 요소

### 컨테이너 생명주기 관리
```python
class UserWorkspace:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.container = None
        
    async def ensure_container(self):
        """사용자 컨테이너가 없으면 생성, 있으면 재사용"""
        if not self.container or not self.container.status == 'running':
            self.container = await self.create_container()
        return self.container
    
    async def send_to_claude(self, message: str) -> str:
        """메시지를 Claude Code CLI로 전달하고 응답 받기"""
        container = await self.ensure_container()
        result = container.exec_run(
            f"echo '{message}' | claude --print",
            user='claude'
        )
        return result.output.decode()
```

### 보안 (최소한)
- 컨테이너 메모리 제한: 1GB
- 네트워크 접근: 필수 도메인만 허용
- 파일 시스템: 사용자별 격리

## 기존 계획 검토 및 누락 요소 보완

### 🔍 검토 결과: 주요 누락 사항 발견

#### 1. **Cloud Run 제약사항 미반영**
- **기존 로그**: "Cloud Run does not support Docker-in-Docker operations"
- **보완**: GKE 또는 Compute Engine 기반 아키텍처로 변경 필요

#### 2. **UX 요구사항 누락**
- **기존 계획**: 상태 표시, UI 컴포넌트, 토큰 사용량 표시
- **보완**: 채팅창에 UI 컴포넌트 통합 필요

#### 3. **에이전트 대시보드 기능 누락**
- **기존 계획**: 에이전트 목록, 실행 로그, 토큰 모니터링
- **보완**: 관리 인터페이스 추가 필요

#### 4. **스케줄링 시스템 누락**
- **기존 계획**: Cloud Scheduler 기반 자동 실행
- **보완**: 에이전트 등록 및 실행 시스템 필요

### 📋 보완된 완전한 아키텍처

#### **플랫폼 변경: GKE 기반**
```yaml
# 기존: Cloud Run (Docker-in-Docker 불가)
# 변경: GKE Autopilot (Docker-in-Docker 지원)
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      securityContext:
        privileged: true  # Docker 소켓 접근 허용
```

#### **UI 컴포넌트 통합**
```html
<!-- 기존: 단순 채팅창 -->
<!-- 보완: 상태 표시 + UI 컴포넌트 -->
<div id="workspace">
    <div id="chat-area">
        <!-- Claude 대화 + 상태 표시 + UI 컴포넌트 -->
    </div>
    <div id="status-bar">
        <!-- [상태 표시: 작업 분석 중...] -->
    </div>
    <div id="agent-dashboard">
        <!-- 에이전트 목록 및 관리 -->
    </div>
</div>
```

#### **에이전트 생명주기 관리**
```python
# 누락된 기능들 추가
class AgentManager:
    async def save_agent(self, agent_config):
        """완성된 에이전트를 DB에 저장"""
        
    async def schedule_agent(self, agent_id, schedule):
        """Cloud Scheduler에 등록"""
        
    async def execute_scheduled_agent(self, agent_id):
        """스케줄된 에이전트 실행"""
        
    async def get_execution_logs(self, agent_id):
        """실행 로그 조회"""
```

### 🎯 완전한 구현 계획 (수정)

#### **1주차: 인프라 구축**
1. **GKE 클러스터 구축**: Docker-in-Docker 지원
2. **사용자 격리**: Pod 기반 워크스페이스
3. **기본 WebSocket API**: 채팅 기능

#### **2주차: 핵심 기능**
1. **UI 컴포넌트 시스템**: 상태 표시, 결과 표시
2. **에이전트 저장**: Firestore 데이터 구조
3. **테스트 실행**: 실시간 피드백

#### **3주차: 자동화 시스템**
1. **에이전트 대시보드**: 목록, 상태 관리
2. **스케줄링**: Cloud Scheduler 통합
3. **실행 모니터링**: 로그, 토큰 사용량

### 📊 데이터 구조 (Firestore)
```javascript
// 기존 계획에서 누락된 상세 구조
agents: {
  [agentId]: {
    name: "주간 주식 분석",
    finalAgentPrompt: "자연어 에이전트 스크립트",
    schedule: { frequency: "weekly", time: "08:00" },
    status: "active" | "inactive",
    totalTokenUsage: { input: 0, output: 0 },
    createdAt: timestamp,
    userId: "user-id"
  }
}

conversations: {
  [conversationId]: {
    messages: [
      {
        role: "user" | "assistant",
        content: "텍스트",
        parts: [{ type: "status", data: "..." }],
        timestamp: timestamp
      }
    ]
  }
}

executions: {
  [executionId]: {
    agentId: "agent-id",
    startTime: timestamp,
    endTime: timestamp,
    status: "success" | "failed",
    result: "실행 결과",
    tokenUsage: { input: 0, output: 0 }
  }
}
```

## 결론

**검토 결과를 반영한 현실적 아키텍처:**

### ✅ 핵심 컨셉 유지
- **1인 1컨테이너**: GKE Pod 기반 구현
- **Claude Code CLI 직접 사용**: 변경 없음
- **실시간 상호작용**: WebSocket + UI 컴포넌트
- **완전한 격리**: Kubernetes 네임스페이스 격리

### 🔧 누락 요소 보완
- **인프라**: Cloud Run → GKE 변경
- **UX**: 상태 표시, UI 컴포넌트, 대시보드 추가
- **자동화**: 스케줄링 시스템 완전 구현
- **데이터**: 상세한 Firestore 스키마 정의

### 🚀 실현 가능성
기존 프로젝트 경험을 바탕으로 Docker-in-Docker 제약사항을 해결하고, 
원래 계획했던 모든 기능을 포함한 완전한 AI 에이전트 플랫폼 구현 가능.

**최종 결과: 기술적 제약사항을 해결하고 모든 요구사항을 만족하는 실용적 아키텍처**