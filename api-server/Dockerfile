# Dockerfile

# 1. 베이스 이미지 선택
# 공식 Python 3.11 슬림 버전을 사용하여 이미지 크기를 최적화합니다.
FROM python:3.11-slim

# 2. 작업 디렉토리 설정
# 컨테이너 내에서 코드가 위치하고 실행될 기본 폴더를 설정합니다.
WORKDIR /app

# 3. 의존성 설치
# requirements.txt 파일을 먼저 복사하여 라이브러리를 설치합니다.
# 이 순서로 진행하면, 코드만 변경되었을 때 불필요한 라이브러리 재설치를 방지하여 빌드 속도를 높일 수 있습니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 복사
# 프로젝트의 모든 파일을 컨테이너의 작업 디렉토리로 복사합니다.
COPY . .

# 5. 서버 실행 포트 설정
# Cloud Run은 기본적으로 8080 포트를 사용합니다.
ENV PORT 8080
EXPOSE 8080

# 6. 서버 실행 명령어
# 컨테이너가 시작될 때 uvicorn을 사용하여 FastAPI 애플리케이션을 실행합니다.
# 0.0.0.0 호스트는 컨테이너 외부의 모든 IP에서 접속을 허용하도록 설정합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
