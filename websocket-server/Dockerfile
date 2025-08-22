FROM python:3.11-slim

WORKDIR /app

# Node.js 및 시스템 패키지 설치 (Claude Code 필수)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Node.js 버전 확인
RUN node --version && npm --version

# Claude Code CLI 사전 설치 (필수)
RUN npm install -g @anthropic-ai/claude-code@latest || \
    npm install -g claude-code || \
    echo "Warning: Claude Code pre-installation failed, will retry at runtime"

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY . .

# 작업 디렉토리 생성
RUN mkdir -p /tmp/workspace-data /app/logs

# 포트 노출
EXPOSE 8000

# 헬스체크 - Claude Code 초기화 시간 고려
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
  CMD curl -f http://localhost:8000/health || exit 1

# 환경변수
ENV PYTHONUNBUFFERED=1
ENV NODE_OPTIONS="--max-old-space-size=2048"

# 실행 명령
CMD ["python", "-u", "main.py"]