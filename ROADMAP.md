# OpenCode API - Feature Roadmap

> TypeScript opencode를 Python API로 포팅하면서 **API 환경에 적합한 기능**만 선별한 로드맵

## 현재 상태 (v0.2.0)

### 구현 완료

**Core:**

- [x] 기본 세션 CRUD
- [x] 메시지 생성/조회
- [x] SSE 스트리밍 응답
- [x] 이벤트 버스 (기본)
- [x] 파일 기반 스토리지

**Providers:**

- [x] Anthropic 프로바이더
- [x] OpenAI 프로바이더
- [x] **LiteLLM 통합 프로바이더 (100+ 모델 지원)**

**Tools:**

- [x] websearch 도구
- [x] webfetch 도구
- [x] todo 도구
- [x] question 도구
- [x] skill 도구 (내장 스킬)

**Agent System (NEW):**

- [x] Agent 모델 정의 (id, name, description, permissions, prompt)
- [x] 기본 agents: build, plan, general, explore
- [x] Beast mode 시스템 프롬프트
- [x] 세션에 agent_id 연결
- [x] Agent routes (`GET/POST /agent`)

**Agentic Loop (NEW):**

- [x] 자동 계속 작업 로직 (tool_use 후 자동 continue)
- [x] 루프 제어 (max_steps, auto_continue, pause_on_question)
- [x] Resume/continue 지원

---

## Phase 1: Core Agent System (Priority: Critical) ✅ COMPLETED

### 1.1 Build Agent 시스템 ✅

> 에이전트 정의 및 시스템 프롬프트 관리

- [x] `Agent` 모델 정의
  - id, name, description
  - system_prompt (beast mode 포함)
  - tools (허용된 도구 목록)
  - permissions (기본 권한)
- [x] 기본 build agent 구현
  - 완전한 시스템 프롬프트
  - 모든 도구 접근 가능
- [x] 세션에 agent 연결
  - `POST /session` 시 agent_id 지정
  - 기본값: build agent

### 1.2 Agentic Loop (Beast Mode) ✅

> todo 목록이 모두 완료될 때까지 자동으로 계속 작업

- [x] 자동 계속 작업 로직
  - 메시지 처리 후 tool_call 상태 확인
  - tool_call이 있으면 자동으로 다음 단계 진행
  - `stop_reason`이 `end_turn`일 때만 종료
- [x] 루프 제어 옵션
  - `max_steps`: 최대 반복 횟수 (기본: 50)
  - `auto_continue`: 자동 계속 여부 (기본: true)
  - `pause_on_question`: question 도구 사용 시 일시 정지
- [x] Beast mode 시스템 프롬프트
  - "todo 완료까지 계속 작업" 지시
  - "resume/continue" 명령 처리

### 1.3 Permission 시스템

> 위험한 도구 실행 전 사용자 승인 요청

- [ ] `Permission` 모델
  - tool_name, action (allow/deny/ask)
  - patterns (glob 패턴)
  - always_allow 목록
- [ ] 승인 요청 흐름
  - SSE로 `permission.ask` 이벤트 전송
  - `POST /permission/{id}/respond` 엔드포인트
  - 타임아웃 처리
- [ ] 기본 권한 규칙
  - websearch, webfetch, todo, skill: 자동 허용
  - question: 자동 허용 (사용자 상호작용)

---

## Phase 2: Provider Integration (Priority: High) ✅ COMPLETED

### 2.1 LiteLLM 통합 ✅

> 100+ LLM 프로바이더를 단일 인터페이스로

- [x] LiteLLM 프로바이더 구현
  - `pip install litellm` 의존성 추가
  - streaming 지원
  - tool calling 지원
- [x] 지원 프로바이더 (LiteLLM 경유)
  - [x] Anthropic (Claude)
  - [x] OpenAI (GPT-4)
  - [x] Google (Gemini)
  - [x] Groq
  - [x] DeepSeek
  - [x] OpenRouter
  - [x] - 100+ more via LiteLLM
- [x] 모델 설정
  - 환경변수로 API 키 관리
  - 모델 ID로 자동 라우팅

### 2.2 모델 Fallback

> 실패 시 대체 모델로 자동 전환

- [ ] fallback 체인 설정
- [ ] 재시도 로직 (지수 백오프)
- [ ] 에러 분류 (rate limit, auth, etc.)

---

## Phase 3: MCP Integration (Priority: High)

### 3.1 MCP Client

> 외부 MCP 서버 연동으로 도구 확장

- [ ] MCP 서버 연결
  - HTTP/SSE 기반 (stdio는 API 환경에서 불가)
  - `POST /mcp` - 서버 추가
  - `GET /mcp` - 서버 목록
  - `DELETE /mcp/{name}` - 서버 제거
- [ ] MCP 도구 가져오기
  - `MCP.tools()` 구현
  - 도구 스키마 변환
  - LLM 세션에 동적 주입
- [ ] MCP 인증
  - API 키 기반
  - OAuth (선택적)

### 3.2 MCP 프롬프트/리소스

- [ ] `MCP.prompts()` - 프롬프트 템플릿
- [ ] `MCP.resources()` - 리소스 접근

---

## Phase 4: Advanced Session Features (Priority: Medium)

### 4.1 세션 고급 기능

- [ ] `POST /session/{id}/fork` - 세션 분기
- [ ] `POST /session/{id}/summarize` - AI 요약 (컨텍스트 압축)
- [ ] `GET /session/{id}/cost` - 비용 계산

### 4.2 Task 도구 (서브에이전트)

> 복잡한 작업을 서브에이전트에게 위임

- [ ] `task` 도구 구현
  - 새 세션 생성
  - 지정된 프롬프트로 작업 수행
  - 결과 반환
- [ ] 서브에이전트 타입
  - explore: 코드베이스 탐색
  - research: 웹 리서치

### 4.3 비용 추적

- [ ] 토큰 사용량 기록
- [ ] 프로바이더별 비용 계산
- [ ] 세션별/전체 비용 집계

---

## Phase 5: External Skill Loading (Priority: Low)

### 5.1 스킬 외부 로드

- [ ] URL에서 스킬 로드
- [ ] GitHub Gist 지원
- [ ] 스킬 캐싱

---

## API 환경에서 제외된 기능

다음 기능들은 로컬 파일시스템 접근이 필요하여 **API 환경에서 구현 불가**:

| 기능                 | 이유                     |
| -------------------- | ------------------------ |
| bash 도구            | 서버에서 쉘 실행 불가    |
| read/write/edit 도구 | 파일시스템 접근 불가     |
| grep/glob/ls 도구    | 파일 검색 불가           |
| LSP 통합             | 언어 서버 실행 불가      |
| PTY/터미널           | 터미널 세션 불가         |
| Snapshot/Patch       | 로컬 파일 변경 추적 불가 |
| IDE 통합             | 로컬 IDE 연동 불가       |
| File watcher         | 파일 변경 감지 불가      |
| ACP (Zed)            | 로컬 IDE 프로토콜        |

---

## 기술 스택

- **Framework**: FastAPI
- **LLM**: LiteLLM (통합 인터페이스)
- **Validation**: Pydantic
- **Streaming**: SSE (Server-Sent Events)
- **Storage**: 파일 기반 JSON (추후 DB 옵션)
- **Deployment**: Docker, HuggingFace Spaces

---

## 구현 순서

```
Phase 1.1 (Build Agent)
    ↓
Phase 1.2 (Agentic Loop)
    ↓
Phase 2.1 (LiteLLM)
    ↓
Phase 1.3 (Permission)
    ↓
Phase 3.1 (MCP Client)
    ↓
Phase 4.2 (Task 도구)
    ↓
Phase 4.1 (세션 고급)
    ↓
Phase 4.3 (비용 추적)
```

---

## 참고

- TypeScript 원본: `/Users/gimjungwook/Projects/opencode/packages/opencode/src`
- Beast mode 프롬프트: `session/prompt/beast.txt`
- Agent 정의: `agent/agent.ts`
- MCP 구현: `mcp/index.ts`
