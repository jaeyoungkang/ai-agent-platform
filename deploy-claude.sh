#!/bin/bash
# Claude Code 최적화 배포 스크립트

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PROJECT_ID="ai-agent-platform-469401"
REGION="asia-northeast3"
REPO="ai-agent-repo"
IMAGE_NAME="api-server"
TAG="claude-optimized-$(date +%Y%m%d-%H%M%S)"

echo -e "${GREEN}=== Claude Code 최적화 배포 시작 ===${NC}"

# 1. Docker 이미지 빌드 (최적화 버전)
echo -e "${YELLOW}1. Docker 이미지 빌드 중...${NC}"
cd websocket-server

docker build \
  --platform linux/amd64 \
  -f Dockerfile.claude \
  -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:${TAG}" \
  -t "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:claude-latest" \
  --no-cache \
  .

if [ $? -ne 0 ]; then
    echo -e "${RED}Docker 빌드 실패!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Docker 이미지 빌드 완료${NC}"

# 2. 이미지 푸시
echo -e "${YELLOW}2. Docker 이미지 푸시 중...${NC}"
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:${TAG}"
docker push "${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:claude-latest"

echo -e "${GREEN}✓ Docker 이미지 푸시 완료${NC}"

# 3. Kubernetes 배포 업데이트
echo -e "${YELLOW}3. Kubernetes 배포 업데이트 중...${NC}"
cd ..

# deployment 이미지 업데이트
kubectl set image deployment/ai-agent-api \
  api-server="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:${TAG}"

# 롤아웃 상태 확인 (최대 5분 대기)
echo -e "${YELLOW}배포 진행 상황 모니터링...${NC}"
kubectl rollout status deployment/ai-agent-api --timeout=5m

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ 배포 성공!${NC}"
    
    # Pod 상태 확인
    echo -e "${YELLOW}Pod 상태:${NC}"
    kubectl get pods -l app=ai-agent-api
    
    # Health check
    echo -e "${YELLOW}Health check 중...${NC}"
    sleep 5
    curl -s https://app.oh-my-agent.info/health | jq '.'
    
    echo -e "${GREEN}=== 배포 완료 ===${NC}"
    echo -e "배포된 이미지: ${TAG}"
else
    echo -e "${RED}배포 실패! 롤백을 고려하세요.${NC}"
    echo -e "${YELLOW}롤백 명령: kubectl rollout undo deployment/ai-agent-api${NC}"
    exit 1
fi