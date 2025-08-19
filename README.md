# AI 에이전트 플랫폼

**Claude Code CLI 기반 AI 에이전트 개발 플랫폼**

![Status](https://img.shields.io/badge/Status-Dashboard%20UX%20Complete-green)
![Architecture](https://img.shields.io/badge/Architecture-1인1컨테이너-blue)
![License](https://img.shields.io/badge/License-Private-red)

## 🎯 핵심 컨셉

> **"사용자는 개별 가상환경에서 Claude Code CLI와 Python 패키지를 이용하여 에이전트를 설계하고 구동한다"**

대시보드 중심의 에이전트 관리 시스템으로, 여러 AI 에이전트를 효율적으로 생성하고 관리할 수 있는 웹 기반 플랫폼입니다.

## 🚀 빠른 시작

### 1. 필수 요구사항
- Docker Desktop
- Python 3.9+
- Node.js 18+ (Docker 이미지용)
- Claude API Key

### 2. 설치 및 실행

```bash
# 1. 저장소 클론
git clone <repository-url>
cd ai-agent-platform

# 2. Docker 워크스페이스 이미지 빌드
docker build -t claude-workspace:latest docker/claude-workspace/

# 3. WebSocket 서버 설정
cd websocket-server
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 4. 환경변수 설정
export ANTHROPIC_API_KEY="your-claude-api-key"

# 5. 서버 실행
python main.py
```

### 3. 브라우저에서 접속
```
http://localhost:8000
```

## 🏗️ 아키텍처

```
대시보드 → 에이전트 선택/생성 → 워크스페이스 → Claude 대화 → 에이전트 완성
    ↓            ↓              ↓           ↓            ↓
  에이전트 관리   워크스페이스 할당   Docker 컨테이너   실시간 통신   Firestore 저장
```

### 핵심 구성요소
- **대시보드 인터페이스**: 에이전트 관리 중심 UI
- **1인 1컨테이너**: 사용자별 독립 환경 (에이전트별 디렉토리 분리)
- **Claude Code CLI**: AI 에이전트 실행 엔진
- **WebSocket API**: 실시간 양방향 통신
- **Firestore**: 에이전트 및 워크스페이스 데이터 저장

## 📁 프로젝트 구조

```
ai-agent-platform/
├── PROJECT_DOCUMENTATION.md    # 완전한 프로젝트 문서
├── README.md                   # 이 파일
├── docker/
│   └── claude-workspace/       # Docker 워크스페이스
│       └── Dockerfile
├── websocket-server/           # 메인 서버
│   ├── main.py                # FastAPI 서버 + 에이전트 관리 API
│   ├── auth.py                # 인증 시스템
│   ├── requirements.txt       # Python 의존성
│   ├── static/
│   │   ├── index.html         # 리다이렉트 페이지
│   │   ├── dashboard.html     # 대시보드 (메인)
│   │   └── workspace.html     # 워크스페이스 (Claude 대화)
│   └── venv/                  # Python 가상환경
└── _documents/                 # 참고 문서들
    ├── plan.md                # 서비스 기획서
    ├── ux.md                  # UX 설계 문서
    └── architecture_improvement_plan.md  # 아키텍처 설계
```

## ✨ 주요 기능

### 현재 구현 완료 (대시보드 UX)
- ✅ **대시보드 중심 UI**: 에이전트 관리 인터페이스
- ✅ **에이전트 CRUD**: 생성, 조회, 수정, 삭제 기능
- ✅ **워크스페이스 시스템**: 세션 기반 Claude 대화 환경
- ✅ **실시간 통계**: 에이전트 수, 실행 횟수, 성공률 표시
- ✅ **1인 1컨테이너**: 효율적 리소스 관리
- ✅ **에이전트별 격리**: 독립 작업 디렉토리 분리
- ✅ **전문적 디자인**: 사무적이고 깔끔한 인터페이스

### 다음 단계 기능
- 🔄 **실행 이력 관리**: 에이전트별 실행 로그 및 결과
- 🔄 **스케줄링 시스템**: 자동 실행 및 알림
- 🔄 **에이전트 마켓플레이스**: 템플릿 공유 및 재사용
- 🔄 **팀 협업**: 에이전트 공유 및 권한 관리

## 📊 성능 지표

| 지표 | 현재 성능 | 설명 |
|------|-----------|------|
| 에이전트 생성 | 즉시 | 컨테이너 재사용으로 즉시 시작 |
| WebSocket 연결 | <1초 | 실시간 대화 연결 |
| Claude 응답 시간 | 2-10초 | Claude API 의존 |
| 대시보드 로딩 | <2초 | 에이전트 목록 및 통계 표시 |
| 동시 사용자 | 100명 (예상) | 1인 1컨테이너 방식 |

## 🔒 보안 특징

- **사용자별 격리**: Docker 컨테이너 기반 독립 환경
- **에이전트별 디렉토리 분리**: `/workspace/agent-{id}` 구조
- **리소스 제한**: 메모리 1GB, CPU 1코어 제한
- **권한 최소화**: 비루트 사용자로 실행
- **API 권한 검증**: 사용자별 에이전트 소유권 확인

## 🚀 배포 계획

### 현재: 대시보드 UX 완성 ✅
- 에이전트 관리 대시보드 구현
- 워크스페이스 시스템 완성
- 전문적 사무 디자인 적용
- 1인 1컨테이너 아키텍처 최적화

### 다음: 프로덕션 배포 🔄
- Google Kubernetes Engine
- 고급 에이전트 기능 (스케줄링, 이력 관리)
- 팀 협업 및 마켓플레이스

## 🤝 기여 가이드

### 개발 환경 설정
```bash
# 개발용 서버 실행 (자동 리로드)
cd websocket-server
source venv/bin/activate
python main.py

# Docker 이미지 재빌드
docker build -t claude-workspace:latest docker/claude-workspace/
```

### 코딩 규칙
- **최소한의 코드 원칙**: 즉시 필요하지 않은 코드는 작성 금지
- **단순성 우선**: 복잡한 구조보다 간단하고 명확한 구조
- **사용자 중심**: 개발자 편의보다 사용자 경험 우선

## 📚 문서

- **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)**: 완전한 프로젝트 문서
- **[_documents/example.md](_documents/example.md)**: 사용자 경험 샘플
- **[websocket-server/README.md](websocket-server/README.md)**: 서버 구현 세부사항

---

**개발 상태**: ✅ MVP 완성 (로컬 환경)  
**다음 목표**: 🚀 GKE 프로덕션 배포  
**최종 업데이트**: 2025년 8월 19일