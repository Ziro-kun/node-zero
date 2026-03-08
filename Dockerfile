FROM python:3.10-slim

# 시스템 패키지 업데이트 및 curl, bash 설치
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# 사용자 요청에 따라 curl을 통한 설치 스크립트 실행 (대화형 모드 비활성화)
RUN curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard --no-prompt

# 파이썬에서 사용할 SDK 등 패키지 설치
RUN pip install --no-cache-dir openclaw tenacity discord.py google-genai ddgs \
    && sed -i 's/TimeoutError,/ConnectionTimeoutError,/' /usr/local/lib/python3.10/site-packages/openclaw/__init__.py || true

# 작업 디렉토리 설정
WORKDIR /workspace

# 컨테이너 실행 시 main.py 구동 (-u 옵션으로 버퍼링 제거)
CMD ["python", "-u", "main.py"]
