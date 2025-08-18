# Dockerfile for Agent Runner Service

# 1. 베이스 이미지 선택
# 공식 Python 3.11 슬림 버전을 사용하여 이미지 크기를 최적화합니다.
FROM python:3.11-slim

# 2. 시스템 업데이트 및 필수 도구 설치
# 패키지 설치 중 필요한 빌드 도구(gcc 등)를 설치합니다.
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 핵심 실행 도구(claude-code-cli) 설치
# 이 서비스의 가장 중요한 목적인 Claude Code Agent Runner CLI를 먼저 설치합니다.
# 실제 CLI 패키지 이름으로 변경해야 합니다.
RUN pip install claude-code-cli

# 5. 실행기 서버 의존성 설치
# FastAPI 서버 구동에 필요한 라이브러리를 설치합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. 소스 코드 복사
# FastAPI 서버 코드를 컨테이너로 복사합니다.
COPY runner_main.py .

# 7. 서버 실행 포트 설정
ENV PORT 8080
EXPOSE 8080

# 8. 서버 실행 명령어
# 컨테이너가 시작될 때 uvicorn을 사용하여 FastAPI 애플리케이션을 실행합니다.
CMD ["uvicorn", "runner_main:app", "--host", "0.0.0.0", "--port", "8080"]
