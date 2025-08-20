# AI 에이전트 플랫폼 - GCP 배포 실행안 (GKE Autopilot)

**작성일**: 2025년 8월 20일  
**목표**: AI 에이전트 제작 및 운용을 위한 1인당 1컨테이너 서비스  
**아키텍처**: GKE Autopilot + Docker-in-Docker, 확장 가능하고 관리 편의성 극대화

---

## 📋 배포 개요

### 🎯 배포 목표
- **서비스 정의**: AI 에이전트 제작 및 운용을 위한 개별 컨테이너 환경 제공
- **관리 편의성**: GKE Autopilot으로 인프라 관리 자동화
- **확장성**: 자동 스케일링으로 사용자 증가에 대응
- **고가용성**: Docker-in-Docker 지원하는 프로덕션 환경

### 🏗️ 현재 상태 점검
```
✅ 로컬 환경 완료:
- AI 에이전트 제작 및 운용 시스템
- 1인 1컨테이너 아키텍처 (사용자별 독립 환경)
- WebSocket 기반 Claude Code CLI 통신
- Firestore 데이터베이스 연동
- 환경변수 보안 강화 (.env.local)

🎯 GCP 이전 대상:
- FastAPI 서버 (websocket-server/)
- Docker 워크스페이스 이미지 (claude-workspace)
- 웹 인터페이스 (dashboard.html, workspace.html)
- 환경변수 및 시크릿 관리
```

---

## 🛠️ GCP 아키텍처 설계 (GKE Autopilot)

### 📊 프로덕션 아키텍처
```
Internet → Cloud Load Balancer → GKE Autopilot Cluster
                                        ↓
                                 [FastAPI Pods]
                                        ↓
                              [User Containers] ←→ Cloud Firestore
                              (1인당 1컨테이너)
                                        ↓
                              Cloud Secret Manager
```

### 🔧 GCP 서비스 구성
| 서비스 | 용도 | 설정 |
|--------|------|------|
| **GKE Autopilot** | 메인 애플리케이션 호스팅 | 완전 관리형, Docker-in-Docker 지원 |
| **Cloud Load Balancer** | HTTPS 종료, 트래픽 분산 | 글로벌 LB + 관리형 SSL 인증서 |
| **Cloud Firestore** | 데이터베이스 | 기존 연동 유지 |
| **Container Registry** | Docker 이미지 저장 | claude-workspace, api-server |
| **Cloud Secret Manager** | 환경변수 보안 관리 | ANTHROPIC_API_KEY 등 |
| **Cloud Monitoring** | 종합 모니터링 | 자동 메트릭 수집 및 알람 |

---

## 🚀 단계별 배포 계획 (GKE Autopilot)

### Phase 1: 기본 인프라 구축 (1일)

#### 1.1 GCP 프로젝트 설정
```bash
# 1. GCP 프로젝트 생성
gcloud projects create ai-agent-platform-prod
gcloud config set project ai-agent-platform-prod

# 2. 필수 API 활성화
gcloud services enable container.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable monitoring.googleapis.com
gcloud services enable dns.googleapis.com

# 3. 권한 설정
gcloud auth configure-docker
```

#### 1.2 GKE Autopilot 클러스터 생성
```bash
# Autopilot 클러스터 생성 (Docker-in-Docker 지원)
gcloud container clusters create-auto ai-agent-cluster \
    --region=asia-northeast3 \
    --release-channel=regular \
    --enable-network-policy

# kubectl 설정
gcloud container clusters get-credentials ai-agent-cluster --region=asia-northeast3
```

#### 1.3 Secret Manager 설정
```bash
# Secret Manager에 환경변수 저장
gcloud secrets create anthropic-api-key --data-file=<(echo "$ANTHROPIC_API_KEY")

# Kubernetes Secret 생성
kubectl create secret generic api-secrets \
    --from-literal=anthropic-api-key="$(gcloud secrets versions access latest --secret=anthropic-api-key)"

# Service Account 권한 설정
gcloud projects add-iam-policy-binding ai-agent-platform-prod \
    --member="serviceAccount:$(kubectl get serviceaccount default -o jsonpath='{.metadata.name}')@ai-agent-platform-prod.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### Phase 2: 컨테이너 이미지 빌드 및 배포 (1일)

#### 2.1 Docker 이미지 빌드 및 푸시
```bash
# 1. Claude 워크스페이스 이미지 빌드
cd docker/claude-workspace
docker build -t gcr.io/ai-agent-platform-prod/claude-workspace:latest .
docker push gcr.io/ai-agent-platform-prod/claude-workspace:latest

# 2. API 서버 이미지 빌드 (Kubernetes 용)
cd ../../websocket-server
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    docker.io \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install -r requirements.txt

# 소스 코드 복사
COPY . .

# 포트 노출
EXPOSE 8000

# 헬스체크 추가
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# 실행 명령
CMD ["python", "main.py"]
EOF

docker build -t gcr.io/ai-agent-platform-prod/api-server:latest .
docker push gcr.io/ai-agent-platform-prod/api-server:latest
```

#### 2.2 Kubernetes 매니페스트 작성
```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-agent-api
  namespace: default
spec:
  replicas: 1  # 비용 최적화: 1개 Pod로 시작
  selector:
    matchLabels:
      app: ai-agent-api
  template:
    metadata:
      labels:
        app: ai-agent-api
    spec:
      securityContext:
        runAsNonRoot: false  # Docker-in-Docker를 위해 필요
      containers:
      - name: api-server
        image: gcr.io/ai-agent-platform-prod/api-server:latest
        ports:
        - containerPort: 8000
        env:
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: api-secrets
              key: anthropic-api-key
        - name: PORT
          value: "8000"
        securityContext:
          privileged: true  # Docker-in-Docker 지원
        volumeMounts:
        - name: docker-sock
          mountPath: /var/run/docker.sock
        - name: workspace-data
          mountPath: /tmp/workspace-data
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: docker-sock
        hostPath:
          path: /var/run/docker.sock
      - name: workspace-data
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: ai-agent-service
spec:
  selector:
    app: ai-agent-api
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP
```

#### 2.3 Ingress 및 HTTPS 설정
```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ai-agent-ingress
  annotations:
    kubernetes.io/ingress.global-static-ip-name: "ai-agent-ip"
    networking.gke.io/managed-certificates: "ai-agent-ssl-cert"
    kubernetes.io/ingress.class: "gce"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
spec:
  rules:
  - host: ai-agent.yourdomain.com
    http:
      paths:
      - path: /*
        pathType: ImplementationSpecific
        backend:
          service:
            name: ai-agent-service
            port:
              number: 80
---
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: ai-agent-ssl-cert
spec:
  domains:
    - ai-agent.yourdomain.com
```

### Phase 3: 네트워킹 및 모니터링 설정 (0.5일)

#### 3.1 정적 IP 및 DNS 설정
```bash
# 정적 IP 예약
gcloud compute addresses create ai-agent-ip --global

# DNS 설정 (도메인이 있는 경우)
gcloud dns managed-zones create ai-agent-zone \
    --dns-name=yourdomain.com \
    --description="AI Agent Platform DNS Zone"

# A 레코드 추가
gcloud dns record-sets transaction start --zone=ai-agent-zone
gcloud dns record-sets transaction add $(gcloud compute addresses describe ai-agent-ip --global --format='value(address)') \
    --name=ai-agent.yourdomain.com \
    --type=A \
    --zone=ai-agent-zone \
    --ttl=300
gcloud dns record-sets transaction execute --zone=ai-agent-zone
```

#### 3.2 Kubernetes 리소스 배포
```bash
# 매니페스트 적용
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/ingress.yaml

# HPA (Horizontal Pod Autoscaler) 설정 (비용 최적화)
kubectl autoscale deployment ai-agent-api --cpu-percent=80 --min=1 --max=3

# 배포 상태 확인
kubectl rollout status deployment/ai-agent-api
kubectl get pods -l app=ai-agent-api
kubectl get ingress ai-agent-ingress
```

### Phase 4: 모니터링 및 로깅 설정 (0.5일)

#### 4.1 Cloud Monitoring 대시보드 설정
```bash
# GKE 클러스터의 기본 모니터링은 자동으로 활성화됨
# 커스텀 대시보드 생성
gcloud monitoring dashboards create --config-from-file=monitoring/dashboard.json
```

#### 4.2 Prometheus 및 Grafana 설치 (선택사항)
```bash
# Helm 설치
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Prometheus Operator 설치
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set grafana.enabled=true \
    --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false

# Grafana 접속 정보 확인
kubectl get secret --namespace monitoring prometheus-grafana \
    -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
```

#### 4.3 애플리케이션 메트릭 설정
```python
# main.py에 추가할 메트릭 코드
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time

# 메트릭 정의
REQUEST_COUNT = Counter('ai_agent_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('ai_agent_request_duration_seconds', 'Request latency')
ACTIVE_CONTAINERS = Counter('ai_agent_active_containers', 'Active user containers')

@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    REQUEST_LATENCY.observe(process_time)
    REQUEST_COUNT.labels(
        method=request.method, 
        endpoint=request.url.path, 
        status=response.status_code
    ).inc()
    
    return response

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

---

## 🔒 보안 설정

### 네트워크 보안
```yaml
# k8s/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: ai-agent-network-policy
spec:
  podSelector:
    matchLabels:
      app: ai-agent-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to: []
    ports:
    - protocol: TCP
      port: 443  # HTTPS
    - protocol: TCP
      port: 53   # DNS
    - protocol: UDP
      port: 53   # DNS
```

### Workload Identity 설정
```bash
# Workload Identity 활성화
gcloud container clusters update ai-agent-cluster \
    --workload-pool=ai-agent-platform-prod.svc.id.goog \
    --region=asia-northeast3

# Google Service Account 생성
gcloud iam service-accounts create ai-agent-gsa

# Kubernetes Service Account 생성
kubectl create serviceaccount ai-agent-ksa

# Workload Identity 바인딩
gcloud iam service-accounts add-iam-policy-binding \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:ai-agent-platform-prod.svc.id.goog[default/ai-agent-ksa]" \
    ai-agent-gsa@ai-agent-platform-prod.iam.gserviceaccount.com

kubectl annotate serviceaccount ai-agent-ksa \
    iam.gke.io/gcp-service-account=ai-agent-gsa@ai-agent-platform-prod.iam.gserviceaccount.com
```

---

## 📊 자동 배포 스크립트

### GKE Autopilot 배포 스크립트
```bash
#!/bin/bash
# deploy-gke.sh

set -e

echo "🚀 AI 에이전트 플랫폼 GKE Autopilot 배포 시작"

PROJECT_ID="ai-agent-platform-prod"
REGION="asia-northeast3"
CLUSTER_NAME="ai-agent-cluster"

# 1. 환경 변수 확인
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다"
    exit 1
fi

# 2. GCP 프로젝트 설정
echo "🔧 GCP 프로젝트 설정 중..."
gcloud config set project $PROJECT_ID

# 3. Docker 이미지 빌드 및 푸시
echo "📦 Docker 이미지 빌드 중..."
docker build -t gcr.io/$PROJECT_ID/claude-workspace:latest docker/claude-workspace/
docker push gcr.io/$PROJECT_ID/claude-workspace:latest

docker build -t gcr.io/$PROJECT_ID/api-server:latest websocket-server/
docker push gcr.io/$PROJECT_ID/api-server:latest

# 4. GKE 클러스터 생성 (존재하지 않으면)
if ! gcloud container clusters describe $CLUSTER_NAME --region=$REGION &>/dev/null; then
    echo "☸️ GKE Autopilot 클러스터 생성 중..."
    gcloud container clusters create-auto $CLUSTER_NAME \
        --region=$REGION \
        --release-channel=regular \
        --enable-network-policy
    
    echo "⏳ 클러스터 초기화 대기 중 (5분)..."
    sleep 300
fi

# 5. kubectl 설정
echo "🔧 kubectl 설정 중..."
gcloud container clusters get-credentials $CLUSTER_NAME --region=$REGION

# 6. Secret 생성
echo "🔐 Secret 생성 중..."
gcloud secrets create anthropic-api-key --data-file=<(echo "$ANTHROPIC_API_KEY") || true
kubectl create secret generic api-secrets \
    --from-literal=anthropic-api-key="$ANTHROPIC_API_KEY" \
    --dry-run=client -o yaml | kubectl apply -f -

# 7. Kubernetes 리소스 배포
echo "🚀 Kubernetes 리소스 배포 중..."
kubectl apply -f k8s/

# 8. 배포 상태 확인
echo "✅ 배포 상태 확인 중..."
kubectl rollout status deployment/ai-agent-api --timeout=300s

# 9. 서비스 URL 출력
echo "🌐 서비스 정보:"
kubectl get ingress ai-agent-ingress
kubectl get service ai-agent-service

echo "✅ 배포 완료!"
echo "📝 SSL 인증서 준비까지 10-20분 소요될 수 있습니다."
```

---

## 📈 비용 및 리소스 계획

### 비용 분석 (월 기준) - 100명 이하 최적화
```
GKE Autopilot (소규모 최적화):
- 기본 클러스터: 무료
- Pod 리소스 (1개 Pod 기준): ~$50/월
  - vCPU: 0.5 코어 (1 Pod × 0.5 코어)
  - 메모리: 1GB (1 Pod × 1GB)

추가 비용:
- Load Balancer: ~$20/월 (또는 NodePort로 $0)
- 네트워크 송신: ~$8/월 (100명 기준)
- Cloud Firestore: ~$3/월 (소규모 사용)
- Container Registry: ~$2/월
- Secret Manager: ~$1/월

총 예상 비용: ~$84/월 (Load Balancer 사용시)
또는 ~$64/월 (NodePort 사용시)
```

### 리소스 사양 및 확장성 (100명 최적화)
```
초기 설정 (비용 최적화):
- Pod 수: 1개 (단일 Pod 시작)
- Pod당 리소스: 1GB RAM, 0.5 CPU
- HPA: 1-3개 Pod 자동 스케일링 (최소화)

확장 시나리오:
- 사용자 1-30명: 1 Pod (기본)
- 사용자 30-70명: 2 Pod (자동 확장)
- 사용자 70-100명: 3 Pod (최대)

예상 성능:
- 동시 사용자: 최대 100명
- 사용자당 컨테이너: 1GB 메모리 제한
- 단순한 가용성: Pod 장애 시 자동 재시작
```

### 자동 스케일링 및 복구 (비용 최적화)
```yaml
# HPA 설정 (비용 최적화)
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ai-agent-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ai-agent-api
  minReplicas: 1  # 최소 1개로 축소
  maxReplicas: 3  # 최대 3개로 제한
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 80  # 더 높은 임계값으로 설정
```

### 추가 비용 절감 옵션
```yaml
# 1. NodePort 서비스 (Load Balancer 대신)
apiVersion: v1
kind: Service
metadata:
  name: ai-agent-nodeport
spec:
  type: NodePort
  selector:
    app: ai-agent-api
  ports:
  - port: 80
    targetPort: 8000
    nodePort: 30000
```

```bash
# 2. Preemptible 노드 사용 (GKE Standard 전환시)
# Autopilot에서는 불가하지만, 추후 옵션으로 고려
gcloud container node-pools create preemptible-pool \
    --cluster=ai-agent-cluster \
    --preemptible \
    --machine-type=e2-medium \
    --num-nodes=1 \
    --max-nodes=3
```

---

## 🧪 테스트 계획

### 배포 전 테스트
```bash
# 로컬 Docker 테스트
docker run -p 8000:8000 gcr.io/$PROJECT_ID/api-server:latest

# Kubernetes 매니페스트 검증
kubectl apply --dry-run=client -f k8s/

# 이미지 빌드 테스트
docker build -t test-api websocket-server/
docker build -t test-workspace docker/claude-workspace/
```

### 배포 후 검증
```bash
# 클러스터 상태 확인
kubectl get nodes
kubectl get pods -l app=ai-agent-api

# 서비스 엔드포인트 확인
INGRESS_IP=$(kubectl get ingress ai-agent-ingress -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# 헬스체크
curl http://$INGRESS_IP/health

# API 테스트
curl -H "X-User-Id: test" http://$INGRESS_IP/api/agents

# HTTPS 테스트 (SSL 인증서 준비 후)
curl https://ai-agent.yourdomain.com/health

# WebSocket 테스트
wscat -c wss://ai-agent.yourdomain.com/workspace/test-user
```

---

## 📋 체크리스트

### 배포 전 준비사항
- [ ] GCP 프로젝트 생성 및 결제 활성화
- [ ] gcloud CLI 설치 및 인증
- [ ] kubectl 설치
- [ ] ANTHROPIC_API_KEY 환경변수 설정
- [ ] 도메인 준비 (DNS 설정)
- [ ] Docker 이미지 빌드 테스트

### 배포 과정
- [ ] GKE Autopilot 클러스터 생성
- [ ] Secret Manager 설정
- [ ] Container Registry에 이미지 푸시
- [ ] Kubernetes 리소스 배포
- [ ] Ingress 및 SSL 설정
- [ ] HPA 설정

### 배포 후 검증
- [ ] 클러스터 상태 확인 (모든 노드 Ready)
- [ ] Pod 상태 확인 (3개 Running)
- [ ] 헬스체크 API 응답 확인
- [ ] 웹 인터페이스 접속 테스트
- [ ] AI 에이전트 생성 테스트
- [ ] WebSocket 연결 테스트
- [ ] Docker-in-Docker 동작 확인
- [ ] SSL 인증서 작동 확인
- [ ] 자동 스케일링 테스트

---

## 🔧 트러블슈팅 가이드

### 주요 문제 해결
1. **Pod 시작 실패**
   ```bash
   # Pod 상태 확인
   kubectl describe pod -l app=ai-agent-api
   
   # Pod 로그 확인
   kubectl logs -l app=ai-agent-api --previous
   
   # Secret 확인
   kubectl get secrets api-secrets -o yaml
   ```

2. **Docker-in-Docker 권한 문제**
   ```bash
   # privileged 설정 확인
   kubectl get deployment ai-agent-api -o yaml | grep privileged
   
   # SecurityContext 확인
   kubectl describe pod -l app=ai-agent-api | grep "Security Context"
   ```

3. **Ingress 접근 불가**
   ```bash
   # Ingress 상태 확인
   kubectl describe ingress ai-agent-ingress
   
   # SSL 인증서 상태 확인
   kubectl describe managedcertificate ai-agent-ssl-cert
   
   # 백엔드 서비스 상태 확인
   kubectl get endpoints ai-agent-service
   ```

4. **이미지 Pull 실패**
   ```bash
   # Service Account 권한 확인
   kubectl describe serviceaccount default
   
   # Container Registry 인증 확인
   gcloud auth configure-docker
   ```

### 로그 및 모니터링
```bash
# 클러스터 로그 확인
kubectl logs -l app=ai-agent-api --tail=100

# 실시간 로그 스트리밍
kubectl logs -l app=ai-agent-api -f

# 클러스터 이벤트 확인
kubectl get events --sort-by=.metadata.creationTimestamp

# 리소스 사용량 확인
kubectl top pods
kubectl top nodes
```

### 롤백 계획
```bash
# 이전 버전으로 롤백
kubectl rollout undo deployment/ai-agent-api

# 특정 리비전으로 롤백
kubectl rollout history deployment/ai-agent-api
kubectl rollout undo deployment/ai-agent-api --to-revision=2

# 스케일 다운 (긴급시)
kubectl scale deployment ai-agent-api --replicas=1
```

---

## 📊 운영 가이드

### 일상 관리 작업
```bash
# 1. 클러스터 상태 확인
kubectl get nodes
kubectl get pods --all-namespaces

# 2. 애플리케이션 상태 확인
kubectl get deployment ai-agent-api
kubectl get hpa ai-agent-hpa

# 3. 리소스 사용량 모니터링
kubectl top pods -l app=ai-agent-api
kubectl describe hpa ai-agent-hpa

# 4. 업데이트 배포
kubectl set image deployment/ai-agent-api api-server=gcr.io/PROJECT_ID/api-server:new-tag
kubectl rollout status deployment/ai-agent-api
```

### 비용 모니터링
```bash
# 현재 월 사용량 확인
gcloud billing accounts list
gcloud billing projects describe ai-agent-platform-prod

# GKE 비용 확인
gcloud container clusters describe ai-agent-cluster --region=asia-northeast3 --format="value(resourceUsage)"

# Pod 리소스 사용량 확인
kubectl describe node | grep -A 5 "Allocated resources"
```

### 백업 및 복구
```bash
# Kubernetes 리소스 백업
kubectl get all -o yaml > backup-$(date +%Y%m%d).yaml

# Firestore 백업 (별도 스크립트)
gcloud firestore export gs://backup-bucket/firestore-$(date +%Y%m%d)

# 복구
kubectl apply -f backup-20250820.yaml
```

---

**준비 완료**: ✅ GKE Autopilot 기반 비용 최적화 배포 계획 완성  
**다음 단계**: 🚀 GCP 프로젝트 생성 및 GKE 클러스터 배포  
**예상 소요 시간**: 2-3일 (100명 이하 최적화 환경)  
**예상 월 비용**: ~$64-84 (60% 비용 절감, 100명 이하 최적화)  
**완료 목표**: AI 에이전트 제작 및 운용 서비스 비용 효율적 오픈