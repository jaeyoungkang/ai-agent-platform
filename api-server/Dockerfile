# Dockerfile

# 1. 베이스 이미지 선택 (Docker-in-Docker 지원)
# Cloud Run에서 Docker 컨테이너를 실행하기 위해 Docker CLI 포함
FROM python:3.11-slim

# 2. 작업 디렉토리 설정
# 컨테이너 내에서 코드가 위치하고 실행될 기본 폴더를 설정합니다.
WORKDIR /app

# 3. Docker CLI 설치 (Docker-in-Docker 지원)
# Cloud Run에서 Docker 컨테이너를 실행하기 위한 Docker CLI 설치
RUN apt-get update && \
    apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

# 4. 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 소스 코드 복사
# 프로젝트의 모든 파일을 컨테이너의 작업 디렉토리로 복사합니다.
COPY . .

# 6. 서버 실행 포트 설정
# Cloud Run은 기본적으로 8080 포트를 사용합니다.
ENV PORT 8080
EXPOSE 8080

# 7. 환경변수 설정
# GCP 프로젝트 정보 (배포 시 동적으로 설정)
ENV PROJECT_ID=ai-agent-platform-469401
ENV REGION=asia-northeast3

# 8. 서버 실행 명령어
# 컨테이너가 시작될 때 uvicorn을 사용하여 FastAPI 애플리케이션을 실행합니다.
# 0.0.0.0 호스트는 컨테이너 외부의 모든 IP에서 접속을 허용하도록 설정합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
