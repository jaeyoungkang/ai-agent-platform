# GitHub 배포 및 도메인 적용 구현안

**작성일**: 2025년 8월 20일  
**프로젝트**: AI Agent Platform  
**도메인**: oh-my-agent.info (GoDaddy)  
**GitHub**: https://github.com/jaeyoungkang/ai-agent-platform.git  

---

## 🎯 구현 목표

### 핵심 목표
- ✅ **GitHub Actions CI/CD**: 자동 빌드/배포 파이프라인 구축
- ✅ **도메인 연결**: oh-my-agent.info → GKE 서비스 연결
- ✅ **HTTPS 적용**: Let's Encrypt 무료 SSL 인증서
- ✅ **환경 분리**: Production 환경 구성

### 예상 결과
```
현재: http://34.64.193.42/static/dashboard.html
변경: https://app.oh-my-agent.info/static/dashboard.html

배포 방식:
현재: 수동 docker build + kubectl apply
변경: git push → GitHub Actions → 자동 배포
```

---

## 📋 상세 구현 계획

### Phase 1: GitHub Actions CI/CD 파이프라인 구축 (2일)

#### 1.1 GitHub Secrets 설정
```yaml
# GitHub Repository Settings > Secrets and variables > Actions
필요한 Secrets:
- GCP_SA_KEY: GCP Service Account JSON Key
- GCP_PROJECT_ID: ai-agent-platform-469401
- GKE_CLUSTER: ai-agent-cluster
- GKE_ZONE: asia-northeast3
- ANTHROPIC_API_KEY: Claude API Key
```

#### 1.2 GitHub Actions 워크플로우 생성
**파일 위치**: `.github/workflows/deploy.yml`
```yaml
name: Deploy to GKE

on:
  push:
    branches: [ main ]
    paths:
    - 'websocket-server/**'
    - 'k8s/**'
    - '.github/workflows/**'
  pull_request:
    branches: [ main ]

env:
  GKE_CLUSTER: ai-agent-cluster
  GKE_ZONE: asia-northeast3
  DEPLOYMENT_NAME: ai-agent-api
  IMAGE: api-server

jobs:
  setup-build-publish-deploy:
    name: Setup, Build, Publish, and Deploy
    runs-on: ubuntu-latest
    environment: production

    permissions:
      contents: read
      id-token: write

    steps:
    - name: Checkout
      uses: actions/checkout@v3

    - id: 'auth'
      name: 'Authenticate to Google Cloud'
      uses: 'google-github-actions/auth@v1'
      with:
        credentials_json: '${{ secrets.GCP_SA_KEY }}'

    - name: 'Set up Cloud SDK'
      uses: 'google-github-actions/setup-gcloud@v1'

    - name: 'Configure Docker'
      run: |-
        gcloud --quiet auth configure-docker gcr.io

    - name: 'Get GKE credentials'
      run: |-
        gcloud container clusters get-credentials "$GKE_CLUSTER" --zone "$GKE_ZONE"

    - name: 'Build Docker image'
      run: |-
        cd websocket-server
        docker build --platform linux/amd64 \
          -t "gcr.io/$PROJECT_ID/$IMAGE:$GITHUB_SHA" \
          -t "gcr.io/$PROJECT_ID/$IMAGE:latest" .
      env:
        PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}

    - name: 'Push Docker image'
      run: |-
        docker push "gcr.io/$PROJECT_ID/$IMAGE:$GITHUB_SHA"
        docker push "gcr.io/$PROJECT_ID/$IMAGE:latest"
      env:
        PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}

    - name: 'Deploy to GKE'
      run: |-
        kubectl set image deployment/$DEPLOYMENT_NAME \
          api-server=gcr.io/$PROJECT_ID/$IMAGE:$GITHUB_SHA
        kubectl rollout status deployment/$DEPLOYMENT_NAME
        kubectl get services -o wide
      env:
        PROJECT_ID: ${{ secrets.GCP_PROJECT_ID }}
```

### Phase 2: 도메인 DNS 설정 (1일)

#### 2.1 GCP Cloud DNS 설정
```bash
# Cloud DNS Zone 생성
gcloud dns managed-zones create oh-my-agent-zone \
    --description="DNS zone for oh-my-agent.info" \
    --dns-name="oh-my-agent.info" \
    --visibility="public"

# A Record 생성 (Load Balancer IP)
gcloud dns record-sets transaction start \
    --zone="oh-my-agent-zone"

gcloud dns record-sets transaction add \
    --name="app.oh-my-agent.info" \
    --ttl=300 \
    --type=A \
    --zone="oh-my-agent-zone" \
    "34.64.193.42"

gcloud dns record-sets transaction execute \
    --zone="oh-my-agent-zone"
```

#### 2.2 GoDaddy DNS 설정
```
GoDaddy DNS Management에서 설정:
- 기존 Nameserver 삭제
- Google Cloud DNS Nameserver로 변경:
  - ns-cloud-d1.googledomains.com
  - ns-cloud-d2.googledomains.com  
  - ns-cloud-d3.googledomains.com
  - ns-cloud-d4.googledomains.com
```

### Phase 3: HTTPS 인증서 및 Ingress 설정 (1일)

#### 3.1 cert-manager 설치
```bash
# cert-manager 설치
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Let's Encrypt ClusterIssuer 생성
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@oh-my-agent.info
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: gce
EOF
```

#### 3.2 Ingress 리소스 생성
**파일 위치**: `k8s/ingress-prod.yaml`
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ai-agent-ingress
  annotations:
    kubernetes.io/ingress.class: gce
    cert-manager.io/cluster-issuer: letsencrypt-prod
    kubernetes.io/ingress.allow-http: "false"
    kubernetes.io/ingress.global-static-ip-name: ai-agent-ip
spec:
  tls:
  - hosts:
    - app.oh-my-agent.info
    secretName: ai-agent-tls
  rules:
  - host: app.oh-my-agent.info
    http:
      paths:
      - path: /*
        pathType: ImplementationSpecific
        backend:
          service:
            name: ai-agent-service
            port:
              number: 80
```

#### 3.3 정적 IP 예약
```bash
# 현재 LoadBalancer IP를 정적 IP로 예약
gcloud compute addresses create ai-agent-ip \
    --global \
    --ip-version=IPV4 \
    --description="Static IP for AI Agent Platform"

# 예약된 IP 확인
gcloud compute addresses describe ai-agent-ip --global
```

### Phase 4: 배포 프로세스 최적화 (1일)

#### 4.1 환경별 Kustomize 설정
**파일 구조**:
```
k8s/
├── base/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── kustomization.yaml
└── overlays/
    └── production/
        ├── ingress.yaml
        ├── certificate.yaml
        └── kustomization.yaml
```

**base/kustomization.yaml**:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
- deployment.yaml
- service.yaml

images:
- name: gcr.io/ai-agent-platform-469401/api-server
  newTag: latest
```

**overlays/production/kustomization.yaml**:
```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: default
namePrefix: prod-

resources:
- ../../base
- ingress.yaml

patchesStrategicMerge:
- deployment-patch.yaml

images:
- name: gcr.io/ai-agent-platform-469401/api-server
  newTag: latest
```

#### 4.2 GitHub Actions 워크플로우 업데이트
```yaml
# 배포 단계에 Kustomize 사용
- name: 'Deploy to GKE with Kustomize'
  run: |-
    kubectl apply -k k8s/overlays/production
    kubectl rollout status deployment/prod-ai-agent-api
```

---

## 🔧 기술적 세부사항

### DNS 전파 및 검증
```bash
# DNS 전파 확인 명령어
nslookup app.oh-my-agent.info 8.8.8.8
dig app.oh-my-agent.info

# HTTPS 인증서 확인
curl -I https://app.oh-my-agent.info
openssl s_client -connect app.oh-my-agent.info:443 -servername app.oh-my-agent.info
```

### 모니터링 및 헬스체크
```yaml
# k8s/base/deployment.yaml에 추가
livenessProbe:
  httpGet:
    path: /health
    port: 8000
    scheme: HTTP
  initialDelaySeconds: 30
  periodSeconds: 10
  
readinessProbe:
  httpGet:
    path: /health  
    port: 8000
    scheme: HTTP
  initialDelaySeconds: 5
  periodSeconds: 5
```

### 보안 설정
```yaml
# 보안 헤더 추가를 위한 Ingress 어노테이션
metadata:
  annotations:
    ingress.gcp.io/force-ssl-redirect: "true"
    cloud.google.com/neg: '{"ingress": true}'
    kubernetes.io/ingress.allow-http: "false"
```

---

## 📊 구현 일정 및 리소스

### 일정 계획 (총 5일)
```
Day 1: GitHub Actions CI/CD 파이프라인 구축
- GitHub Secrets 설정
- Workflow 파일 생성 및 테스트
- 첫 자동 배포 검증

Day 2: DNS 및 도메인 설정  
- Cloud DNS Zone 생성
- GoDaddy Nameserver 변경
- DNS 전파 대기 및 확인

Day 3: HTTPS 인증서 설정
- cert-manager 설치
- Ingress 리소스 생성  
- SSL 인증서 발급 및 확인

Day 4: 배포 최적화 및 테스트
- Kustomize 구성
- 전체 워크플로우 테스트
- 성능 및 보안 검증

Day 5: 모니터링 및 문서화
- 배포 프로세스 문서화
- 장애 대응 가이드 작성
- 팀 온보딩 자료 준비
```

### 필요 리소스
```
👨‍💻 인력
- DevOps 엔지니어: 40시간 (1주)
- 테스트 및 검증: 8시간

💰 추가 비용
- 도메인 비용: 이미 구입 완료
- 정적 IP 예약: $1.46/월
- SSL 인증서: 무료 (Let's Encrypt)
- 추가 GCP 비용: 거의 없음
```

---

## ⚠️ 위험 요소 및 대응 방안

### 주요 위험 요소
```
🔴 높은 위험
1. DNS 전파 지연 (24-48시간)
   → 대응: 단계적 전환, TTL 최소화

2. HTTPS 인증서 발급 실패
   → 대응: HTTP 우선 구성, 수동 인증서 백업

3. 기존 서비스 중단 가능성
   → 대응: Blue-Green 배포, 즉시 롤백 계획

🟡 중간 위험
1. CI/CD 파이프라인 권한 문제
   → 대응: Service Account 권한 사전 검증

2. GKE Ingress 구성 복잡성
   → 대응: 단계별 테스트, LoadBalancer 백업
```

### 롤백 계획
```bash
# 긴급 롤백 명령어
kubectl rollout undo deployment/ai-agent-api

# DNS 롤백 (필요시)
# GoDaddy에서 A Record를 기존 IP로 변경

# GitHub Actions 비활성화
# Repository Settings > Actions > Disable workflows
```

---

## ✅ 성공 기준

### 기능적 성공 기준
- [ ] https://app.oh-my-agent.info 접근 가능
- [ ] SSL 인증서 정상 작동 (A+ 등급)
- [ ] GitHub push 시 자동 배포 성공
- [ ] 기존 기능 모든 정상 작동

### 성능 기준
- [ ] 페이지 로딩 시간 < 3초
- [ ] API 응답 시간 < 2초  
- [ ] 99.9% 가용성 달성
- [ ] 배포 시간 < 5분

### 보안 기준
- [ ] HTTPS 강제 리다이렉트
- [ ] 보안 헤더 적용
- [ ] SSL Labs A+ 등급
- [ ] 취약점 스캔 통과

---

## 🎯 구현 승인 후 진행 순서

### 즉시 실행 가능한 작업
1. **GitHub Secrets 설정** (10분)
2. **GitHub Actions 워크플로우 생성** (30분)  
3. **첫 자동 배포 테스트** (20분)

### 외부 의존성 작업
1. **GoDaddy DNS 설정** (DNS 전파 대기 필요)
2. **SSL 인증서 발급** (도메인 검증 필요)

### 최종 검증 작업
1. **전체 시스템 테스트**
2. **성능 및 보안 검증**
3. **문서화 및 인수인계**

---

**구현 준비 상태**: ✅ 모든 사전 조건 충족  
**예상 완료**: 5일 (DNS 전파 시간 포함)  
**위험도**: 🟡 중간 (충분한 롤백 계획 보유)  
**추천도**: ⭐⭐⭐⭐⭐ 강력 추천

이 구현안을 검토하시고 승인해 주시면 순차적으로 작업을 진행하겠습니다.