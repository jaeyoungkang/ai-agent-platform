FROM python:3.9-slim

WORKDIR /app

# 의존성 설치
COPY api-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY api-server/ .

# 정적 파일 디렉토리 생성
RUN mkdir -p static

# 정적 파일 복사 (index.html)
COPY index.html ./static/index.html

# 포트 노출
EXPOSE 8080

# 서버 시작
CMD ["python", "main.py"]