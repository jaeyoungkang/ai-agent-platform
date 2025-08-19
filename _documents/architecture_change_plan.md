# AI 에이전트 플랫폼 아키텍처 변경 계획안 (MVP)

**작성일**: 2025-01-18  
**프로젝트 성격**: MVP - 최소 동작 구현 우선

## 📋 변경 배경

### 1월 18일 작업 성과
- runner_main.py에서 Claude Code CLI 실행 성공
- 최종 명령어: `["claude", "--print", "--output-format", "json", "--permission-mode", "acceptEdits"]`
- stdin 방식 프롬프트 전달 검증

### 현재 상황
- Docker-in-Docker는 Cloud Run에서 동작하지 않음
- 기존 코드는 모두 삭제하고 새로 구현

## 🎯 MVP 목표

**단일 목표**: 사용자 요청을 받아 Claude Code를 실행하고 결과를 반환하는 최소한의 동작하는 시스템

## 🏗️ MVP 아키텍처 (사용자 격리 유지)

### 핵심 유지 기능 (user_isolation_implementation.md 기반)

**필수 유지사항**:
- **사용자별 격리**: 각 요청마다 독립된 실행 환경
- **Docker 컨테이너 격리**: 파일 시스템, 프로세스, 메모리 완전 분리
- **보안성**: 네트워크 격리 (`--network=none`)
- **리소스 제한**: `--memory=1g --cpus=1`
- **자동 정리**: `--rm` 플래그로 컨테이너 자동 삭제

### MVP 구현 방식: Cloud Build 기반 격리

**구조**: FastAPI → Cloud Build API → 독립된 실행 환경

**Cloud Build 스텝 (격리된 환경)**:
```yaml
steps:
- name: 'python:3.9'
  entrypoint: 'bash'
  args:
  - '-c'  
  - |
    pip install claude-cli
    echo "${_PROMPT}" | claude --print --output-format json --permission-mode acceptEdits
```

**API 서버 주요 엔드포인트**:
- **POST `/api/conversation`**: 대화형 에이전트 (Cloud Build 격리)
- **POST `/agents/{id}/run`**: 에이전트 실행 (Cloud Build 격리)
- **GET `/agents`**: 에이전트 목록 (Firestore 연동)

**프론트엔드 (frontend_implementation.md 기반)**:
- **단일 HTML 파일**: index.html (Vanilla JS + TailwindCSS CDN)
- **채팅 인터페이스**: Claude Code CLI를 웹으로 표현
- **상태 표시**: `[상태 표시: 처리 중...]` 
- **UI 컴포넌트**: 동적 HTML 컴포넌트 표시
- **코드 최소화**: 프레임워크 없이 극단적 단순함

**기존 Docker-in-Docker를 Cloud Build로 교체하되 격리 수준은 동일하게 유지**

## 📝 구현 단계

### 1단계: Docker-in-Docker 제거
- [ ] 기존 Docker 컨테이너 실행 코드를 Cloud Build API 호출로 교체
- [ ] runner_main.py 삭제 (이미 API 서버로 통합됨)
- [ ] Docker 의존성 제거하되 기능은 보존

### 2단계: Cloud Build 연동
- [ ] Cloud Build API 클라이언트 추가
- [ ] 기존 엔드포인트 유지하되 실행 방식만 변경:
  - `/api/conversation` → Cloud Build 호출
  - `/agents/{id}/run` → Cloud Build 호출
- [ ] Firestore 연동 유지 (대화 기록, 에이전트 정보)

### 3단계: 프론트엔드 단순화
- [ ] 기존 index.html을 단일 파일로 통합 (frontend_implementation.md 기준)
- [ ] TailwindCSS CDN 적용 (커스텀 CSS 제거)
- [ ] Vanilla JavaScript로 단순화 (프레임워크 제거)
- [ ] API 응답 형식 통일 (`text`, `status`, `component`, `agentCreated`)

### 4단계: Cloud Build 설정 및 배포
- [ ] cloudbuild.yaml 작성
- [ ] GCP 프로젝트에서 테스트
- [ ] Cloud Run 배포 (Docker-in-Docker 의존성 없이)
- [ ] 정적 파일 서빙 설정 (index.html)

## 🎯 검증된 요소 활용

1월 18일 테스트 성공 요소:
- 명령어: `claude --print --output-format json --permission-mode acceptEdits`
- stdin 프롬프트 전달
- JSON 응답 파싱

## 💡 MVP 효과

1. **단순함**: 복잡한 코드 모두 제거
2. **동작함**: Cloud Build로 격리 환경 확보
3. **배포됨**: Cloud Run 호환성 문제 해결
4. **빠른 개발**: 프론트엔드 단일 HTML 파일로 1일 완성 가능
5. **코드 최소화**: TailwindCSS CDN + Vanilla JS로 학습 시간 제거

## 🎨 프론트엔드 특징 (frontend_implementation.md 기반)

**극단적 단순화**:
- 단일 HTML 파일 (190줄, 모든 기능 포함)
- 프레임워크 없음 (Vanilla JavaScript)
- 커스텀 CSS 없음 (TailwindCSS CDN)
- 복잡한 상태 관리 없음 (전역 변수)

**Claude Code CLI 웹 표현**:
- 채팅 인터페이스로 터미널 대화 구현
- 상태 표시: `[상태 표시: 처리 중...]`
- UI 컴포넌트: 동적 HTML 표시
- 에이전트 생성 완료 알림