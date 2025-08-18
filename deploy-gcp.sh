#!/bin/bash

# GCP Cloud Run 배포 스크립트
# 3단계: GCP Cloud Run 배포 준비

set -e

# 환경변수 설정
export PROJECT_ID=ai-agent-platform-469401
export REGION=asia-northeast3
export SERVICE_NAME=ai-agent-platform
export IMAGE_NAME=api-server-gcp

echo "=== GCP Cloud Run 배포 시작 ==="
echo "프로젝트: $PROJECT_ID"
echo "리전: $REGION"
echo "서비스: $SERVICE_NAME"
echo "이미지: $IMAGE_NAME"

# 1. GCP 인증 확인
echo "1. GCP 인증 상태 확인..."
gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -1

# 2. 프로젝트 설정 확인
echo "2. 프로젝트 설정 확인..."
gcloud config set project $PROJECT_ID

# 3. 필요한 API 활성화
echo "3. 필요한 GCP API 활성화..."
gcloud services enable \
  cloudbuild.googleapis.com \
  cloudrun.googleapis.com \
  artifactregistry.googleapis.com \
  --project=$PROJECT_ID || echo "API 권한 부족 - 수동으로 활성화 필요"

# 4. Artifact Registry 생성
echo "4. Artifact Registry 생성..."
gcloud artifacts repositories create $IMAGE_NAME \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID || echo "레포지토리가 이미 존재하거나 권한 부족"

# 5. Docker 이미지 태그 및 푸시
echo "5. Docker 이미지 태그 및 푸시..."
IMAGE_URL="$REGION-docker.pkg.dev/$PROJECT_ID/$IMAGE_NAME/$IMAGE_NAME:latest"
docker tag $IMAGE_NAME:latest $IMAGE_URL
docker push $IMAGE_URL

# 6. Cloud Run 배포
echo "6. Cloud Run에 배포..."
gcloud run deploy $SERVICE_NAME \
  --image=$IMAGE_URL \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300s \
  --max-instances=10 \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,REGION=$REGION,GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --project=$PROJECT_ID

# 7. 배포 결과 확인
echo "7. 배포 완료!"
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME \
  --region=$REGION \
  --format="value(status.url)" \
  --project=$PROJECT_ID)

echo "서비스 URL: $SERVICE_URL"
echo "헬스체크: curl $SERVICE_URL/"

echo "=== GCP Cloud Run 배포 완료 ==="