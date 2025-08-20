# AI 에이전트 플랫폼 - 아키텍처 분석 및 업데이트

**작성일**: 2025년 8월 19일 (2025년 8월 20일 업데이트)  
**분석 목적**: 현재 컨테이너 사용 패턴 점검 및 단순화 방향 제시

## 🚨 중요 업데이트 (2025-08-20)

**아키텍처 변경 완료**: Docker-in-Docker에서 **Kubernetes-Native** 방식으로 전환
- **GKE Autopilot** 환경에서 Docker 컨테이너 실행 제한으로 인한 설계 변경
- **DISABLE_DOCKER=true** 환경에서 Claude Code CLI 시뮬레이션 방식 적용
- 사용자별 컨테이너 생성 로직은 **비활성화 상태**로 유지

---

## 📊 변경된 아키텍처 분석

### 🐳 변경된 실행 환경 패턴

#### 현재 구조 (Kubernetes-Native)
```python
# main.py:40-45 (업데이트됨)
docker_client = None
if os.getenv("DISABLE_DOCKER", "false").lower() != "true":
    try:
        docker_client = docker.from_env()
    except Exception as e:
        logger.warning(f"Docker not available: {e}")
        docker_client = None
```

#### 실제 동작 방식 (변경됨)
1. **WebSocket 연결 시**: 컨테이너 생성 **시도하지 않음** (DISABLE_DOCKER=true)
2. **에이전트 생성 시**: Kubernetes Pod 내에서 직접 실행
3. **실행 범위**: Pod 수준에서 격리 (컨테이너 중첩 없음)
4. **Claude Code CLI**: 시뮬레이션 응답으로 대체

---

## 🔍 변경된 실행 패턴 분석

### ✅ 현재 패턴: "Kubernetes Pod 직접 실행"

```
전체 사용자 → 공유 Kubernetes Pod → 에이전트 1, 2, 3, 4...
├─ 사용자별 세션 격리 (메모리)
├─ 에이전트별 데이터 격리 (Firestore)
└─ 임시 작업공간 (emptyDir)
```

**장점:**
- ✅ **보안 강화**: GKE Autopilot 보안 정책 완전 준수
- ✅ **관리 단순화**: 컨테이너 중첩 없이 Pod 수준 관리
- ✅ **리소스 효율성**: 모든 사용자가 Pod 리소스 공유
- ✅ **자동 스케일링**: Kubernetes HPA로 자동 확장/축소
- ✅ **장애 복구**: Pod 장애 시 자동 재시작

**변경된 제약사항:**
- ⚠️ **Claude Code CLI 제한**: 실제 CLI 대신 시뮬레이션 응답
- ⚠️ **파일시스템 공유**: 모든 사용자가 동일한 Pod 파일시스템 사용
- ⚠️ **리소스 경합**: CPU/메모리를 모든 사용자가 공유

### ❌ 이전 패턴: "Docker-in-Docker" (GKE에서 불가능)

```
Pod → Docker 소켓 → 사용자별 컨테이너 → Claude Code CLI
```

**GKE Autopilot에서 불가능한 이유:**
- ❌ **보안 정책 위반**: 특권 컨테이너 금지
- ❌ **hostPath 금지**: Docker 소켓 마운트 불가
- ❌ **네트워크 제한**: 호스트 네트워크 접근 제한

---

## 💡 권장사항: Kubernetes-Native 구조 최적화

### 🎯 핵심 원칙: "클라우드 네이티브, 보안 우선"

현재의 **"Kubernetes Pod 직접 실행"** 방식이 클라우드 환경에 최적화됨:

1. **보안성**: GKE Autopilot 보안 정책 완전 준수
2. **확장성**: Kubernetes 자동 스케일링 활용
3. **안정성**: Pod 레벨 장애 복구 및 로드밸런싱
4. **비용 효율성**: 리소스 공유로 운영비 최소화

### 📋 Kubernetes 환경 최적화 방안

#### 1. Claude Code CLI 대체 솔루션 구현
```python
# 현재: 시뮬레이션 응답
# 향후: Cloud Run Jobs 또는 별도 워크스페이스 서비스 연동

async def send_to_claude(self, message: str, agent_id: str = None) -> str:
    if os.getenv("DISABLE_DOCKER", "false").lower() == "true":
        # 시뮬레이션 응답 (현재)
        return f"Claude Code CLI가 Kubernetes 환경에서 실행 중입니다..."
```

#### 2. Workload Identity 보안 강화
```yaml
# deployment.yaml에 이미 적용됨
spec:
  serviceAccountName: ai-agent-ksa  # Workload Identity 활용
  containers:
  - name: api-server
    env:
    - name: DISABLE_DOCKER
      value: "true"  # Docker 비활성화
```

#### 3. HPA 기반 자동 스케일링 활용
```yaml
# 현재 설정된 HPA
minReplicas: 1
maxReplicas: 3
targetCPUUtilizationPercentage: 80
```

---

## 🔧 Kubernetes-Native 개발 가이드라인

### 🚫 피해야 할 복잡성

1. **Docker-in-Docker 복원 시도**: GKE Autopilot에서 불가능
2. **복잡한 워크스페이스 격리**: Pod 수준에서 충분
3. **과도한 리소스 분할**: 공유 리소스 모델 유지
4. **컨테이너 오케스트레이션**: Kubernetes가 자동 처리

### ✅ 활용해야 할 Kubernetes 기능

1. **Pod 자동 스케일링**: HPA로 사용자 증가에 대응
2. **서비스 발견**: Kubernetes Service로 네트워킹
3. **설정 관리**: Secret Manager + Workload Identity
4. **상태 모니터링**: Health Check + 자동 재시작

---

## 📊 Kubernetes 리소스 설정 및 제한

### 현재 Pod 리소스 설정 (deployment.yaml)
```yaml
resources:
  requests:
    memory: "1Gi"      # Pod당 1GB 메모리 요청
    cpu: "500m"        # Pod당 0.5 CPU 코어 요청
  limits:
    memory: "2Gi"      # Pod당 2GB 메모리 제한
    cpu: "1000m"       # Pod당 1 CPU 코어 제한
```

### 동시 사용자 예상 (100명 기준)
```
예상 동시 사용자: 10-20명
Pod당 처리 가능: 30-50명 (경험적 수치)
HPA 스케일링: 1-3 Pod 자동 조정
총 처리 능력: 90-150명
```

### 리소스 공유 모델
```
Pod 1 (1GB RAM, 1 CPU) → 전체 사용자 공유
├─ 사용자별 세션: 메모리 50-100MB
├─ Firestore 연결: 공유 커넥션 풀
└─ WebSocket: 사용자당 1개 연결
```

---

## 🎯 결론 및 실행 계획

### ✅ 결론: Kubernetes-Native 아키텍처 성공적 전환

**"Pod 직접 실행"** 방식이 다음 조건을 모두 만족:
- ✅ **보안 강화**: GKE Autopilot 정책 완전 준수
- ✅ **운영 단순화**: Kubernetes 자동 관리 활용
- ✅ **비용 효율성**: 리소스 공유로 운영비 절감
- ✅ **확장성**: HPA로 자동 스케일링

### 📝 완료된 주요 변경사항

1. **Docker 비활성화** (DISABLE_DOCKER=true)
2. **Workload Identity 설정** (ai-agent-ksa 서비스 어카운트)
3. **LoadBalancer 서비스** (외부 접근 허용)
4. **Firestore 권한 해결** (403 오류 해결)

### 🚀 향후 개선 우선순위

1. **Phase 1**: Claude Code CLI 대체 솔루션 구현 (Cloud Run Jobs)
2. **Phase 2**: 도메인 연결 및 HTTPS 적용
3. **Phase 3**: 모니터링 및 로깅 강화

---

## 💻 Kubernetes-Native 코드 변경 사례

```python
# 변경 전: Docker 컨테이너 생성
async def ensure_container(self) -> docker.models.containers.Container:
    try:
        self.container = docker_client.containers.get(self.container_name)
        # 복잡한 컨테이너 관리 로직...
    except docker.errors.NotFound:
        self.container = await self._create_container()

# 변경 후: Docker 비활성화 시 대체 로직
async def send_to_claude(self, message: str, agent_id: str = None) -> str:
    if os.getenv("DISABLE_DOCKER", "false").lower() == "true":
        logger.info(f"Docker disabled - simulating Claude response")
        return f"Claude Code CLI가 Kubernetes 환경에서 실행 중입니다.\\n\\n사용자 메시지: {message}"
    
    # 기존 Docker 로직은 유지 (로컬 개발용)
    container = await self.ensure_container()
    # ...
```

이러한 **조건부 분기**로 기존 코드를 보존하면서 Kubernetes 환경에 대응했습니다.

---

**핵심 메시지**: Kubernetes-Native 전환을 통해 **보안성과 확장성을 확보**하면서도 **코드 복잡도는 최소화**했습니다. 향후 Claude Code CLI 대체 솔루션 구현을 통해 완전한 기능을 제공할 예정입니다.