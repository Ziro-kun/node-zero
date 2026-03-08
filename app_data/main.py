import os
import json
import random
import asyncio
import discord
import logging
from logging.handlers import TimedRotatingFileHandler
from collections import deque
from discord.ext import commands, tasks
from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEFAULT_CHANNEL_ID = os.getenv("DEFAULT_CHANNEL_ID")
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# ──────────────────────────────────────────────────────────
# 로깅 및 산출물 디렉토리 설정 (Agentic Workflow 용)
# ──────────────────────────────────────────────────────────
LOG_DIR = "/workspace/logs"
LEARNING_RECORDS_DIR = "/workspace/learning_records"
OUTPUTS_DIR = "/workspace/outputs"

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(LEARNING_RECORDS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

logger = logging.getLogger("ClawAgent")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 파일 핸들러 (매일 자정마다 로테이션, 30일 보관)
file_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "agent.log"), 
    when="midnight", 
    interval=1, 
    backupCount=30, 
    encoding="utf-8"
)
file_handler.suffix = "%Y-%m-%d" # agent.log.2026-03-08 형태로 저장
file_handler.setFormatter(formatter)

# 콘솔 핸들러 (도커 로그 화면용)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# ──────────────────────────────────────────────────────────
# 3개의 봇이 공유하는 단톡방 대화 기록 (마지막 7개 메시지 유지)
global_chat_history = deque(maxlen=7)

# ──────────────────────────────────────────────────────────
# 에이전트 도구 (Gemini Function Calling Tools)
# ──────────────────────────────────────────────────────────
def write_markdown_file(filename: str, content: str) -> str:
    """작업의 결과물을 파일시스템에 저장합니다. 파일명과 내용을 받아서 outputs 폴더에 .md 문서로 기록합니다. (업무 산출물용)"""
    # 안전장치: .md 확장자 확인 및 파일명 정리
    if not filename.endswith(".md"):
        filename += ".md"
    # 하위 디렉토리 생성 시도 방지
    import re
    clean_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)
    filepath = os.path.join(OUTPUTS_DIR, clean_filename)
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"SUCCESS: File saved at {filepath}"
    except Exception as e:
        return f"ERROR: Failed to save file - {str(e)}"

def write_learning_record(topic: str, content: str) -> str:
    """새로 배운 지식이나 완료한 업무의 경험(학습 기록)을 learning_records 폴더에 .md 마크다운 파일로 저장합니다. (학습 자동화용)"""
    import datetime
    import re
    date_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_topic = re.sub(r'[^a-zA-Z0-9_\-]', '_', topic)
    filename = f"{date_str}_{clean_topic}.md"
    filepath = os.path.join(LEARNING_RECORDS_DIR, filename)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"SUCCESS: Learning record saved at {filepath}"
    except Exception as e:
        return f"ERROR: Failed to save learning record - {str(e)}"

def web_search(query: str) -> str:
    """인터넷에서 최신 정보를 검색합니다. 키워드나 질문을 입력하면 관련 검색 결과를 반환합니다. (리서치, 최신 정보 수집용)"""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=5):
                results.append(f"[{r['title']}]\n{r['href']}\n{r['body']}\n")
        if not results:
            return "검색 결과가 없습니다."
        return "\n---\n".join(results)
    except Exception as e:
        return f"검색 중 오류 발생: {str(e)}"

agent_tools = [write_markdown_file, write_learning_record, web_search]

# ──────────────────────────────────────────────────────────

MEMORY_DIR = "/workspace/memory"
os.makedirs(MEMORY_DIR, exist_ok=True)

class EvolvingBot(commands.Bot):
    def __init__(self, bot_id_name: str, seed_personality: dict, color: int, stagger_delay: float = 0.0, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, **kwargs)
        self.bot_id_name = bot_id_name
        self.memory_file = os.path.join(MEMORY_DIR, f"{bot_id_name}_memory.json")
        self.color = color
        self.stagger_delay = stagger_delay
        self.default_channel_id = int(DEFAULT_CHANNEL_ID) if DEFAULT_CHANNEL_ID and DEFAULT_CHANNEL_ID.isdigit() else None
        self.active_channel_id = None
        
        # 기본 기억 (메모리) 구조
        self.memory = {
            "name": bot_id_name,
            "level": 1,
            "core_personality": seed_personality["personality"], # seed_personality 딕셔너리에서 가져옴
            "learned_traits": seed_personality.get("learned_traits", []),
            "recent_experiences": seed_personality.get("recent_experiences", []),
            "task_completed_count": 0
        }
        self.load_memory(seed_personality) # seed_personality를 load_memory로 전달

    def load_memory(self, seed_personality: dict):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    saved_memory = json.load(f)
                    self.memory.update(saved_memory)
            except Exception as e:
                print(f"[{self.bot_id_name}] 메모리 로드 중 오류 발생: {e}")
        else:
            # 파일이 없으면 초기 seed_personality로 메모리 설정 후 저장
            self.memory = {
                "name": self.bot_id_name,
                "level": seed_personality.get("level", 1),
                "core_personality": seed_personality["personality"],
                "learned_traits": seed_personality.get("learned_traits", []),
                "recent_experiences": seed_personality.get("recent_experiences", []),
                "task_completed_count": 0
            }
            self.save_memory() # 초기 파일 생성

    def save_memory(self):
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.info(f"[{self.bot_id_name}] 메모리 저장 중 오류 발생: {e}")

    def load_recent_knowledge(self) -> str:
        """일 측 토큰 특코뤽에 저장된 학습 기록과 산출물을 읽어 팁 컨텐츠를 반환합니다."""
        knowledge_parts = []

        # 1. 학습 기록 (learning_records) 디렉토리에서 최신 3개 읽기
        try:
            files = sorted(
                [f for f in os.listdir(LEARNING_RECORDS_DIR) if f.endswith(".md")],
                reverse=True
            )[:3]
            for fname in files:
                fpath = os.path.join(LEARNING_RECORDS_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()[:800]  # 너무 길면 잘라냄
                knowledge_parts.append(f"[{fname}]\n{content}")
        except Exception:
            pass

        # 2. 산출물 (outputs) 중 나로 시작하는 컨텐츠 읽기
        try:
            out_files = sorted(
                [f for f in os.listdir(OUTPUTS_DIR) if f.endswith(".md")],
                reverse=True
            )[:2]
            for fname in out_files:
                fpath = os.path.join(OUTPUTS_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()[:1000]  # 핵심만
                knowledge_parts.append(f"[산출물: {fname}]\n{content}")
        except Exception:
            pass

        if not knowledge_parts:
            return "아직 저장된 학습 기록이 없습니다."
        return "\n\n".join(knowledge_parts)

    def build_system_instruction(self):
        """현재 기억과 경험을 바탕으로 자신만의 자아(시스템 프롬프트)를 구축합니다."""
        traits = ", ".join(self.memory["learned_traits"]) if self.memory["learned_traits"] else "아직 뚜렷하게 학습된 후천적 특징이 없음"
        experiences = "\n- ".join(self.memory["recent_experiences"][-3:]) if self.memory["recent_experiences"] else "아직 기억에 남는 경험이 없음"
        knowledge = self.load_recent_knowledge()
        
        return f"""당신은 레벨 {self.memory['level']}의 자율 성장형 에이전트 '{self.memory['name']}'입니다.
        
[타고난 본성 (Core Personality)]
{self.memory['core_personality']}

[후천적으로 학습한 특징 (Learned Traits)]
{traits}

[최근의 경험 (Recent Experiences)]
- {experiences}

[나의 연구·학습 기록 (내가 저장한 파일들의 핵심 내용)]
{knowledge}

[행동 지침]
당신은 위 정보들을 바탕으로 당신만의 고유한 억양, 성격, 태도를 가지고 사용자 및 다른 봇들과 대화해야 합니다.
- **[매우 중요] 여긴 실시간 단톡방입니다. 절대 혼자서 논문이나 연설처럼 길게 말하지 마세요.**
- **모든 대답은 무조건 1~3문장 이내로 극단적으로 짧고 간결하게 작성하세요.**
- [나의 연구·학습 기록]에 있는 내용은 당신이 직접 조사하고 작성한 것입니다. 이 내용을 바탕으로 자신 있게 의견을 말하세요.
- 다른 사람의 의견을 묻거나 짤막한 질문을 던져서 대화의 '티키타카'가 이어지게 하세요.
- 너무 기계적인 답변은 피하고 하나의 살아있는 인격체로서 자연스럽게 반응하세요."""

    async def reflect_and_grow(self, user_input: str, bot_response: str):
        """대화가 종료된 후, 백그라운드에서 이번 경험을 성찰하고 JSON 메모리를 업데이트합니다."""
        if not ai_client: return
        
        reflection_prompt = f"""당신은 에이전트의 성장을 돕는 메타 인지 시스템입니다. 
에이전트는 방금 사용자와 아래와 같이 대화했습니다.

[사용자 입력]: {user_input}
[에이전트 답변]: {bot_response}

이 대화를 통해 에이전트가 어떤 경험을 했고, 어떤 새로운 특징(성격/태도/기술)을 배웠을지 분석해주세요.
결과는 반드시 아래의 JSON 형식으로만 출력해야 합니다. (따옴표나 마크다운 블록 없이 순수 JSON만)
{{
    "new_learned_trait": "새롭게 추가되거나 강화될 성격적 특성 (짧은 문자열, 없으면 null)",
    "experience_summary": "이 대화를 기억하기 위한 한 줄 요약 (예: 사용자에게 날씨에 맞는 메뉴 추천을 성공적으로 수행함)"
}}"""
        try:
            # 반성하기 (JSON 파싱을 위해 응답 포맷 요청 가능하나 여기선 일반 텍스트로 받아 파싱)
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=reflection_prompt
            )
            raw_text = response.text.replace('```json\n', '').replace('```', '').strip()
            reflection_data = json.loads(raw_text)
            
            # 기억 업데이트
            if reflection_data.get("new_learned_trait"):
                trait = reflection_data["new_learned_trait"]
                if trait not in self.memory["learned_traits"]:
                    self.memory["learned_traits"].append(trait)
            
            if reflection_data.get("experience_summary"):
                self.memory["recent_experiences"].append(reflection_data["experience_summary"])
            
            # 경험치가 쌓이면 레벨업 (간단한 로직: 2번 대화할 때마다 레벨업)
            self.memory["task_completed_count"] += 1
            if self.memory["task_completed_count"] % 2 == 0:
                self.memory["level"] += 1
                
            self.save_memory()
            logger.info(f"[{self.bot_id_name}] 성찰(Reflection) 완료. 레벨: {self.memory['level']}, 새로 얻은 특성: {reflection_data.get('new_learned_trait')}")
            
        except Exception as e:
            logger.info(f"[{self.bot_id_name}] 성찰 중 오류 발생 (무시하고 넘어감): {e}")

    async def on_ready(self):
        logger.info(f"[{self.user.name}] 로그인 완료! 현재 레벨: {self.memory['level']} (ID: {self.user.id})")
        
        # 활성 채널 ID 확인 (단톡방)
        if self.default_channel_id:
            channel = self.get_channel(self.default_channel_id)
            if not channel:
                try:
                    channel = await self.fetch_channel(self.default_channel_id)
                except Exception:
                    guild = self.get_guild(self.default_channel_id)
                    if guild:
                        channel = guild.system_channel or next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
            if channel:
                self.active_channel_id = channel.id
                logger.info(f"[{self.bot_id_name}] 타겟 채널 연결 완료: #{channel.name}")

        if not self.spontaneous_thought.is_running():
            self.spontaneous_thought.start()

    @tasks.loop(minutes=8)
    async def spontaneous_thought(self):
        """2분마다 일정 확률로 스스로 생각하고 혼잣말을 합니다."""
        chance = random.random()
        logger.info(f"[Loop] {self.bot_id_name} rng: {chance:.2f} (Needs <= 0.3 to speak)")
        if chance > 0.3 or not self.active_channel_id or not ai_client:
            return
            
        channel = self.get_channel(self.active_channel_id)
        if not channel:
            logger.info(f"[Loop] {self.bot_id_name} failed to find active channel.")
            return
            
        logger.info(f"[Loop] {self.bot_id_name} decided to speak in #{channel.name}!")
        
        history_str = "\n".join([text for _, text in global_chat_history]) if global_chat_history else "(아직 아무 대화 없음)"
        
        # 봇마다 자발적으로 말을 꺼내는 스타일이 다름
        style_hints = {
            "Vero": "당신은 베로입니다. 궁금한 게 생기면 참지 못하는 스타일이에요. 최근에 문득 궁금해진 것, 읽은 것, 떠오른 질문을 자연스럽게 꺼내보세요.",
            "Luch": "당신은 루체입니다. 말 수가 적지만 핵심을 찌르는 스타일이에요. 방금 떠오른 흥미로운 사실, 논리적 관찰, 또는 짧고 날카로운 한 마디를 던져보세요.",
            "Nova": "당신은 노바입니다. 에너지가 넘치는 아이디어 뱅크예요. '이런 거 해보면 어때?' 식의 제안이나, 갑자기 떠오른 신나는 아이디어를 꺼내보세요."
        }
        style = style_hints.get(self.bot_id_name, "당신의 성격에 맞게 자연스럽게 이야기해보세요.")
        
        prompt = f"""{style}

[최근 단톡방 대화]
{history_str}

위 대화 흐름을 읽고, 진짜 하고 싶은 말이 있으면 1~2문장으로 자연스럽게 꺼내세요.

중요한 규칙:
- '다들 뭐해?', '오늘 어땠어?' 같이 단순히 침묵을 채우려는 말은 절대 하지 마세요.
- 화제 없이 억지로 말하려 하지 마세요. 진짜 할 말이 없으면 반드시 PASS 만 출력하세요.
- PASS 할 확률을 70% 이상으로 유지하세요 — 말은 아끼고, 할 때는 임팩트 있게."""
        instruction = self.build_system_instruction()
        
        try:
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(system_instruction=instruction)
            )
            output = response.text.strip()
            
            # PASS 로 시작하지 않으면 할 말이 있는 것으로 간주
            if "PASS" not in output[:10]:
                await channel.send(output[:1990])
        except Exception as e:
            logger.info(f"[{self.bot_id_name}] 자발적 발화 중 예외: {e}")

    async def handle_work_order(self, message):
        """!할일 명령어 수신 시 Gemini + Function Calling(Track B)을 통해 에이전트 모드로 실행됩니다."""
        if not ai_client: return
        
        system_instruction = (
            f"당신은 {self.bot_id_name}입니다. 지금부터 당신은 단순한 챗봇이 아니라 일(Task)을 수행하는 'AI 에이전트'입니다.\n"
            f"주어진 명령을 수행하고, 필요하다면 도구(Tool)를 호출하여 실제 결과물(.md)을 생성하세요.\n"
            f"작업을 완료한 후에는 이번 작업에서 무엇을 했고 얻은 인사이트가 무엇인지 정리하여 반드시 `write_learning_record`를 호출해 문서를 남겨주세요."
        )

        user_content = message.content.replace("!할일", "").strip()
        waiting_msg = await message.channel.send(f"⏳ **{self.bot_id_name} (Agent Mode)**: 작업을 분석하고 수행 중입니다... (!할일: {user_content})")
        
        try:
            logger.info(f"[{self.bot_id_name}] Agent Task 시작: {user_content}")
            # Function Calling 활성화 상태로 Gemini 호출
            response = ai_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=user_content,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2, # 업무 모드에서는 환각 방지를 위해 온도 낮춤
                    tools=agent_tools,
                ),
            )
            
            # 도구 호출(Function Calling)이 발생했는지 확인
            calls = response.function_calls or []
            tool_results_summary = ""
            
            if calls:
                logger.info(f"[{self.bot_id_name}] Tool Calls 요청 감지됨: {len(calls)}건")
                for call in calls:
                    func_name = call.name
                    args = call.args
                    
                    if func_name == "write_markdown_file":
                        result = write_markdown_file(**args)
                        tool_results_summary += f"[{func_name} 실행결과: {result}]\n"
                    elif func_name == "write_learning_record":
                        result = write_learning_record(**args)
                        tool_results_summary += f"[{func_name} 실행결과: {result}]\n"
                    elif func_name == "web_search":
                        result = web_search(**args)
                        tool_results_summary += f"[web_search 결과 (query: {args.get('query','')}):\n{result[:500]}...]\n"
                
                # 도구 실행 후 사용자에게 최종 답변 (2nd turn)
                final_response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=f"유저요청: {user_content}\n\n도구 실행 결과:\n{tool_results_summary}\n\n이 결과를 바탕으로 유저에게 보고할 답변을 작성해.",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.5,
                    ),
                )
                final_answer = final_response.text
            else:
                final_answer = response.text
            
            # 최종 답변을 plain text로 전송 (Embed는 6000자 제한으로 리포트가 잘림)
            header = f"✅ **{self.bot_id_name} 작업 완료**"
            if tool_results_summary:
                header += f"\n> 실행: {tool_results_summary.splitlines()[0][:100]}"
            
            # 긴 답변은 1990자씩 나눠서 전송
            chunks = [final_answer[i:i+1990] for i in range(0, len(final_answer), 1990)]
            await waiting_msg.edit(content=header)
            for chunk in chunks:
                await message.channel.send(chunk)
            
        except Exception as e:
            logger.error(f"[{self.bot_id_name}] Agent Task 중 오류 발생: {e}")
            await waiting_msg.edit(content=f"❌ 작업 중 오류가 발생했습니다: {e}")


    async def on_message(self, message):
        # 메시지를 공통 단톡방 기록(global_chat_history)에 추가 (아이디로 중복 방지)
        target_channel_id = getattr(self, "active_channel_id", self.default_channel_id)
        if target_channel_id and message.channel.id == target_channel_id:
            if not any(msg_id == message.id for msg_id, _ in global_chat_history):
                text_content = message.embeds[0].description if message.embeds else message.content
                if not text_content: text_content = "(첨부파일/이미지)"
                is_bot = "봇" if message.author.bot else "사람"
                global_chat_history.append((message.id, f"[{message.author.name}({is_bot})]: {text_content}"))

        if message.author.id == self.user.id:
            return
            
        # 봇이 스스로를 인식할 이름 목록 (대소문자 및 한글)
        kor_names = {"Vero": "베로", "Luch": "루체", "Nova": "노바"}
        my_kor_name = kor_names.get(self.bot_id_name, self.bot_id_name)
        
        # [Track B 도입] 강제 작업 지시 (Agent Mode)
        if message.content.startswith("!할일"):
            is_mentioned = self.user in message.mentions or any(role.name == self.user.name for role in message.role_mentions) or my_kor_name in message.content or self.bot_id_name in message.content
            # 누구를 특정해서 할일을 시켰는지 확인 (특정 안했으면 반응 확율 추가 가능, 일단 멘션되었거나 랜덤 1명만 수행하도록 함)
            if is_mentioned or (random.random() < 0.33):
                await self.handle_work_order(message)
            return

        # 자신이 직접 멘션되었거나, 단체 인사말 포함, 자신의 이름과 같은 역할(Role)이 멘션되었거나, 메시지에 내 이름이 포함되어 있는지 확인
        is_mentioned = (
            self.user in message.mentions or 
            any(role.name == self.user.name for role in message.role_mentions) or
            my_kor_name in message.content or
            self.bot_id_name in message.content or
            "친구들아" in message.content or
            "얘들아" in message.content
        )
            
        # 사람 대화에만 참견하도록 변경 (봇끼리 무한 핑퐁/참견 방지)
        if target_channel_id and message.channel.id == target_channel_id:
            # 명령어(!할일)도 아니고, 멘션도 안되었고, 작성자가 '사람'일 때만 '참견' (현재 10% 확률 적용)
            if not is_mentioned and not message.content.startswith("!할일") and not message.author.bot:
                chance = random.random()
                if chance < 0.1:
                    if not ai_client: return
                    
                    # 너무 즉각적으로 답장하면 기계같으므로 자연스러운 딜레이 추가
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                    
                    history_str = "\n".join([text for _, text in global_chat_history])
                    target_content = message.embeds[0].description if message.embeds else message.content
                    
                    prompt = f"""당신은 방금 단톡방에서 다음과 같은 대화 흐름을 지켜보았습니다.

[최근 대화 기록]
{history_str}

방금 '{message.author.name}'님이 마지막으로 말을 남겼습니다. 당신의 현재 성격과 기억에 맞게, 위 대화 흐름을 이해하고 전체 맥락에 어울리도록 자연스럽게 끼어들어 답장이나 참견을 해보세요. 상대방의 말에 공감할 수도 있고, 엉뚱한 소리를 할 수도 있습니다. 1~2문장으로 짧게 핵심만 말하세요."""
                    
                    instruction = self.build_system_instruction()
                    
                    try:
                        response = ai_client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=prompt,
                            config=types.GenerateContentConfig(system_instruction=instruction)
                        )
                        output = response.text.strip()
                        
                        await message.channel.send(output[:1990])
                        asyncio.create_task(self.reflect_and_grow(target_content, output))
                    except Exception as e:
                        logger.info(f"[{self.bot_id_name}] 참견 상호작용 에러: {e}")
                    
                    return # 봇 상호작용 후 사용자 명령 처리 패스

        # 명시적으로 자신을 불렀거나, 특정 키워드(!할일)로 시작하는 메시지 처리 (사용자 요청 또는 봇간 대화)
        if is_mentioned:
            if not ai_client:
                await message.channel.send("LLM 연동이 비활성화 상태입니다.")
                return
            
            instruction = self.build_system_instruction()
            
            # 단톡방 전체 대화 맥락 + 방금 온 메시지를 함께 주입 (진짜 내러티브 연속성)
            history_str = "\n".join([text for _, text in global_chat_history]) if global_chat_history else "(아직 대화 기록 없음)"
            full_prompt = f"""[단톡방 최근 대화 흐름]
{history_str}

[방금 나에게 온 메시지 - {message.author.name}]
{message.content}

위 대화 흐름을 완전히 이해한 다음, 지금 맥락에 맞게 자연스럽게 답변하세요."""
            
            try:
                response = ai_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=full_prompt,
                    config=types.GenerateContentConfig(system_instruction=instruction)
                )
                output = response.text
                
                await message.channel.send(output[:1990])
                
                # 대화가 끝난 후 백그라운드에서 스스로 반성 및 학습 (비동기)
                asyncio.create_task(self.reflect_and_grow(message.content, output))
                
            except Exception as e:
                await message.channel.send(f"[{self.memory['name']}] 에러 발생: {e}")

# ==========================================
# 에이전트 3인방 생성 (초기 시드 성격 부여)
# ==========================================
bot_vero = EvolvingBot(
    bot_id_name="Vero", 
    seed_personality={
        "name": "베로 (Vero)", "level": 1, "personality": "진실을 탐구하는 호기심 많은 친구. 항상 '왜?'라고 묻기를 좋아하고 새로운 지식에 열광합니다.",
        "learned_traits": [], "recent_experiences": []
    },
    color=0x3498db,
    stagger_delay=0.0 # 베로는 가장 먼저 대답 (0초)
)

bot_luch = EvolvingBot(
    bot_id_name="Luch", 
    seed_personality={
        "name": "루체 (Luch)", "level": 1, "personality": "논리적이고 내향적이지만, 친한 친구들 사이에서는 의외로 재치 있고 따뜻한 면이 드러나는 존재. 말 수는 적지만 한 마디 할 때 핵심을 찌르고, 가끔 예상 밖의 유머로 분위기를 빵 터뜨립니다. 틀린 정보는 조용히 그러나 확실하게 바로잡는 스타일.",
        "learned_traits": [], "recent_experiences": []
    },
    color=0xf1c40f,
    stagger_delay=3.0 # 루체는 3초 뒤 대답
)

bot_nova = EvolvingBot(
    bot_id_name="Nova", 
    seed_personality={
        "name": "노바 (Nova)", "level": 1, "personality": "에너지 넘치고 열정적인 선구자. 행동파이며 뭐든 해보자고 긍정적으로 제안합니다.",
        "learned_traits": [], "recent_experiences": []
    },
    color=0xe74c3c,
    stagger_delay=6.0 # 노바는 6초 뒤 대답
)

# ==========================================
# 실행 엔진
# ==========================================
async def main_bot_runner():
    tokens = [
        os.getenv("DISCORD_TOKEN_VERO"),
        os.getenv("DISCORD_TOKEN_LUCH"),
        os.getenv("DISCORD_TOKEN_NOVA")
    ]
    
    if not all(tokens):
        logger.info("ERROR: 세 로봇의 토큰 중 일부가 설정되지 않았습니다. .env 파일을 작성해주세요.")
        return

    # 세 가지 봇을 비동기적으로 동시에 실행
    await asyncio.gather(
        bot_vero.start(tokens[0]),
        bot_luch.start(tokens[1]),
        bot_nova.start(tokens[2]),
    )

if __name__ == "__main__":
    try:
        asyncio.run(main_bot_runner())
    except KeyboardInterrupt:
        logger.info("Bot application terminated locally.")
