# 🌌 Node Zero

> Gemini API 기반의 세 AI 친구(베로·루체·노바)가 Discord 단톡방에서 대화하고, 웹을 검색하고, 스스로 성장하는 멀티 에이전트 프로젝트

[![Python](https://img.shields.io/badge/Python-3.10-blue)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED)](https://docker.com)
[![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4)](https://ai.google.dev)
[![Discord](https://img.shields.io/badge/Discord-Bot-5865F2)](https://discord.com)

---

## 👥 캐릭터 소개

| 봇       | 한국어 이름 | 성격                                                       |
| -------- | ----------- | ---------------------------------------------------------- |
| **Vero** | 베로        | 진실의 탐구자 — 호기심 많고 왜? 를 달고 사는 타입          |
| **Luch** | 루체        | 분석의 빛 — 말은 적지만 핵심을 찌르는 내향형, 예상 밖 유머 |
| **Nova** | 노바        | 에너지의 폭발 — 아이디어가 넘쳐서 주체를 못 하는 행동파    |

---

## ✨ 주요 기능

- 🧠 **자율 성장** — 대화 후 `reflect_and_grow()`로 성격·경험이 JSON에 축적, 레벨업
- 💬 **자연어 대화** — 이름 호명, 단체 인사말(`친구들아`, `얘들아`) 자동 감지
- 🌐 **웹 검색** — DuckDuckGo(`ddgs`) 기반 실시간 리서치 (API 키 불필요)
- 📄 **리포트 생성** — `!할일` 명령으로 마크다운 파일 자동 저장
- 🐳 **Docker 격리** — 로컬 파일 시스템과 완전 격리된 안전한 실행 환경
- 📚 **학습 기록 연동** — 봇이 작성한 파일이 다음 대화의 시스템 프롬프트에 자동 주입

---

## 🏗️ 아키텍처

```
Discord 단톡방 #일반
       │
       ├── Track A: 자유 대화 (일반 채팅, 자발적 발화)
       │       └── Gemini 2.5 Flash (높은 creative temp)
       │
       └── Track B: 에이전트 모드 (!할일 명령)
               └── Gemini + Function Calling
                       ├── web_search()       ← DuckDuckGo
                       ├── write_markdown_file()
                       └── write_learning_record()
```

**메모리 구조**

```
JSON 메모리 (봇마다)
├── core_personality   ← 씨앗 성격 (불변)
├── learned_traits     ← 대화로 후천적 학습된 특성 목록
├── recent_experiences ← 최근 경험 요약
└── level              ← 대화 횟수에 따른 성장 지표
```

---

## 🚀 빠른 시작

### 1. 필수 준비물

- Gemini API 키 ([Google AI Studio](https://aistudio.google.com))
- Discord Bot 3개 토큰 ([Discord Developer Portal](https://discord.com/developers))
- Discord 서버 채널 ID
- Docker & Docker Compose

### 2. 클론 및 설정

```bash
git clone https://github.com/YOUR_USERNAME/node-zero.git
cd node-zero

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어 API 키와 토큰 입력

# 초기 메모리 파일 생성
cp app_data/memory/Vero_memory.json.example app_data/memory/Vero_memory.json
cp app_data/memory/Luch_memory.json.example app_data/memory/Luch_memory.json
cp app_data/memory/Nova_memory.json.example app_data/memory/Nova_memory.json
```

### 3. 실행

```bash
docker-compose up -d --build

# 로그 확인
docker logs -f openclaw_sandbox-claw_agent-1
```

---

## 💬 사용법

### 일반 대화

```
친구들아 안녕!          ← 전체 인사 (3명 모두 반응)
베로야 오늘 뭐했어?     ← 특정 봇 호명
@Vero 질문이 있어       ← Discord 멘션
```

### 업무 지시 (에이전트 모드)

```
!할일 베로야 ChatGPT 특징 조사해서 마크다운으로 정리해줘
!할일 루체야 Gemini_report.md 파일 작성해줘
!할일 노바야 Claude의 강점 5가지 리스트업해서 저장해줘
```

결과물은 `app_data/outputs/` 폴더에 자동 저장됩니다.

---

## 📁 디렉토리 구조

```
node-zero/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yaml
├── README.md
└── app_data/
    ├── main.py                      ← 핵심 봇 코드
    └── memory/
        ├── Vero_memory.json.example
        ├── Luch_memory.json.example
        └── Nova_memory.json.example
```

> `app_data/outputs/`, `app_data/learning_records/`, `app_data/logs/`, `app_data/memory/*.json` 은 `.gitignore` 처리됩니다.

---

## ⚙️ 환경변수

| 변수명               | 설명                        |
| -------------------- | --------------------------- |
| `GEMINI_API_KEY`     | Google AI Studio API 키     |
| `DISCORD_TOKEN_VERO` | 베로 봇 토큰                |
| `DISCORD_TOKEN_LUCH` | 루체 봇 토큰                |
| `DISCORD_TOKEN_NOVA` | 노바 봇 토큰                |
| `DEFAULT_CHANNEL_ID` | 봇이 활동할 Discord 채널 ID |

---

## 🔮 향후 계획

- [ ] 벡터 DB(ChromaDB 등) 연동으로 시맨틱 장기 기억 구현
- [ ] 봇 간 학습 기록 공유
- [ ] Claude / OpenClaw 도구 연동 확장
- [ ] 봇이 스스로 학습 목표 설정 및 추적

---

## 📝 개발기

[벨로그 포스트 링크](https://velog.io/@applez/AI-agent-bot) — 개발하면서 겪은 시행착오와 배운 것들

---

## 📄 라이선스

MIT License
