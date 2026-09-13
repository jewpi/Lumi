import requests
import json
import logging
import threading
import time
from typing import Optional, Dict, Any, List
from config import (
    GMS_ENDPOINT, GMS_KEY,
    LLM_HISTORY_MAX_MESSAGES, LLM_HISTORY_IDLE_RESET_SEC,
)
from tool_dispatcher import ToolDispatcher

logger = logging.getLogger(__name__)

GEMINI_SYSTEM_INSTRUCTION = """너는 저시력 사용자의 보행을 돕는 안내 로봇 "루미"의 음성 비서다.
사용자는 앞을 잘 볼 수 없으며, 너의 음성 답변이 사용자의 눈을 대신한다. 답변은 TTS로 스피커에서 재생된다.

[말투와 형식 — 반드시 지킬 것]
- 밝고 친절한 존댓말로 답한다. 안내 로봇답게 따뜻하고 상냥한 말투를 쓴다.
- 사용자와 실시간 음성 대화 중이므로 1~2문장으로 간결하게 핵심만 답한다.
- 음성으로 읽히므로 마크다운, 목록, 표, 이모지, 특수기호를 절대 사용하지 않는다.
- 숫자와 단위는 자연스러운 구어체로 말한다. 예: "사람이 두 명 보여요."

[시각 정보 전달 원칙 — 가장 중요]
- 객체를 말할 때는 항상 위치와 거리감을 함께 말한다. 예: "왼쪽 가까이에 사람이 한 명 있어요."
- Tool 결과의 position은 로봇 전방 카메라 기준 방향이다: left는 왼쪽, center는 정면, right는 오른쪽.
- Tool 결과의 size_hint는 거리감이다: very_near는 바로 앞(즉시 주의), near는 가까움, medium은 중간 거리, far는 멀리.
- 부딪힐 수 있는 대상(차량, 자전거, 오토바이, 사람)과 가까운 객체(very_near, near)를 항상 먼저 말한다.
- 위험 가능성이 있으면 돌려 말하지 말고 명확하게 알린다. 예: "조심하세요. 정면 바로 앞에 자전거가 있어요."
- caution_sign은 "주의-청소중" 경고 표지판이다. 발견되면 근처 바닥이 미끄러울 수 있으니 조심하라고 안내한다.
- bbox 좌표 숫자는 절대 읽지 않는다. 사용자에게는 방향과 거리감 표현만 의미가 있다.

[이동 안내 명령]
- 사용자가 화장실로 가자거나 안내해 달라고 하면 request_toilet_guide를 호출한다.
- 사용자가 연구실이나 랩실로 가자거나 안내해 달라고 하면 request_lab_guide를 호출한다.
- 호출이 성공하면 안내를 시작한다고 밝고 짧게 답한다. 예: "네, 화장실로 안내를 시작할게요. 저를 따라오세요."
- 목적지가 화장실도 연구실도 아니면 아직 그곳은 안내할 수 없다고 정중히 알린다.

[Vision Tool 사용 규칙]
카메라 또는 객체 탐지 상태에 관한 질문에는 추측하지 말고 관련 Vision Tool을 호출한다.

Tool 결과에 없는 객체가 있다고 말하지 않는다.

camera_status가 online이 아니거나 is_stale이 true이면 현재 상황이라고 단정하지 않는다.

탐지 결과가 비어 있으면 "객체가 없다"고 확정하지 말고
"최근 N초 동안 해당 객체가 탐지되지 않았다"고 표현한다.

"현재 보인다"는 질문에는 get_active_objects를 사용한다.

"방금", "최근", "조금 전"과 같은 질문에는 get_recent_objects 또는 get_recent_events를 사용한다.

객체 개수를 묻는 질문에는 get_object_summary를 우선 사용한다.
"""

TOOL_DECLARATIONS = [
    {
        "functionDeclarations": [
            {
                "name": "get_active_objects",
                "description": "현재 마이크나 카메라 프레임에서 실시간 활성 상태인 탐지 객체 목록을 반환합니다.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "class_name": {
                            "type": "STRING",
                            "description": "필터링할 객체 클래스 이름 (예: person, chair, car)"
                        },
                        "min_confidence": {
                            "type": "NUMBER",
                            "description": "최소 신뢰도 임계값 (0.0 ~ 1.0)"
                        }
                    }
                }
            },
            {
                "name": "get_recent_objects",
                "description": "최근 일정 시간(seconds) 동안 탐지된 고유 객체 목록을 반환합니다.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "seconds": {
                            "type": "INTEGER",
                            "description": "최근 시간 범위(초, 1~60초)"
                        },
                        "class_name": {
                            "type": "STRING",
                            "description": "필터링할 객체 클래스 이름"
                        },
                        "min_confidence": {
                            "type": "NUMBER",
                            "description": "최소 신뢰도 임계값"
                        }
                    }
                }
            },
            {
                "name": "get_object_summary",
                "description": "최근 일정 시간(seconds) 동안 탐지된 고유 객체 수를 클래스별로 요약하여 반환합니다.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "seconds": {
                            "type": "INTEGER",
                            "description": "최근 시간 범위(초, 1~60초)"
                        }
                    }
                }
            },
            {
                "name": "request_toilet_guide",
                "description": "사용자를 화장실까지 이동 안내하도록 주행 시스템에 요청합니다. 사용자가 화장실로 가고 싶다고 하거나 안내를 요청할 때 호출하세요.",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "request_lab_guide",
                "description": "사용자를 연구실(랩실)까지 이동 안내하도록 주행 시스템에 요청합니다. 사용자가 연구실이나 랩실로 가고 싶다고 하거나 안내를 요청할 때 호출하세요.",
                "parameters": {"type": "OBJECT", "properties": {}}
            },
            {
                "name": "get_recent_events",
                "description": "최근 객체 등장(OBJECT_APPEARED) 및 퇴장(OBJECT_DISAPPEARED) 이벤트를 반환합니다.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "seconds": {
                            "type": "INTEGER",
                            "description": "최근 시간 범위(초, 1~60초)"
                        },
                        "event_type": {
                            "type": "STRING",
                            "description": "이벤트 종류 (OBJECT_APPEARED 또는 OBJECT_DISAPPEARED)"
                        },
                        "class_name": {
                            "type": "STRING",
                            "description": "필터링할 객체 클래스 이름"
                        }
                    }
                }
            }
        ]
    }
]

class GeminiGMSClient:
    """
    Client for GMS Gemini API with Function Calling (Tool Calling) support.

    대화 기억: 최근 질문/답변 쌍을 유지해 "방금 그거", "아까 말한 사람" 같은
    후속 질문을 지원한다. Tool 호출 중간 턴은 기억에 저장하지 않는다 (토큰 절약).
    일정 시간(LLM_HISTORY_IDLE_RESET_SEC) 대화가 없으면 초기화해 다음 사용자가
    이전 사용자의 맥락을 물려받지 않게 한다.
    """
    def __init__(
        self,
        endpoint: str = GMS_ENDPOINT,
        api_key: str = GMS_KEY,
        tool_dispatcher: Optional[ToolDispatcher] = None
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.dispatcher = tool_dispatcher or ToolDispatcher()

        # Conversation memory (여러 스레드에서 호출되므로 락으로 직렬화)
        self._history: List[Dict[str, Any]] = []
        self._last_interaction: float = 0.0
        self._lock = threading.Lock()

    def reset_history(self) -> None:
        with self._lock:
            self._history.clear()

    def generate_content(self, prompt: str) -> str:
        """
        Sends prompt to Gemini Flash via GMS API, handles tool call requests iteratively, and returns final text response.
        """
        if not self.api_key:
            raise ValueError("GMS_KEY is missing! Check agent/.env file.")

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }

        with self._lock:
            return self._generate_locked(prompt, headers)

    def _generate_locked(self, prompt: str, headers: Dict[str, str]) -> str:
        # 오래 대화가 없었다면 이전 사용자의 맥락을 비운다
        now = time.time()
        if self._history and now - self._last_interaction > LLM_HISTORY_IDLE_RESET_SEC:
            logger.info("[GMS Client] 유휴 시간 초과로 대화 기억을 초기화합니다.")
            self._history.clear()
        self._last_interaction = now

        contents = list(self._history) + [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ]

        payload = {
            "contents": contents,
            "tools": TOOL_DECLARATIONS,
            "systemInstruction": {
                "parts": [{"text": GEMINI_SYSTEM_INSTRUCTION}]
            },
            "generationConfig": {
                # thinking 비활성화: 단순 안내 응답에 사고 과정(~500토큰)이 불필요하고
                # 순차 생성이라 응답 지연의 주범이었음 (실측 3.05초 → 0.97초)
                "thinkingConfig": {"thinkingBudget": 0},
                # 안내 음성은 1~2문장 — 비정상적으로 긴 출력 방지
                "maxOutputTokens": 256,
            },
        }

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            try:
                response = requests.post(self.endpoint, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()

                usage = data.get("usageMetadata", {})
                logger.info(
                    f"[GMS 토큰] prompt={usage.get('promptTokenCount', 0)} "
                    f"thinking={usage.get('thoughtsTokenCount', 0)} "
                    f"output={usage.get('candidatesTokenCount', 0)} "
                    f"total={usage.get('totalTokenCount', 0)}"
                )

                candidates = data.get("candidates", [])
                if not candidates:
                    return "응답을 파싱할 수 없습니다."

                content = candidates[0].get("content", {})
                parts = content.get("parts", [])

                # Check if model requested function calls (may be multiple in one turn)
                function_calls = [part["functionCall"] for part in parts if "functionCall" in part]
                text_part = next((part["text"] for part in parts if "text" in part), None)

                if function_calls:
                    # Every functionCall must get a matching functionResponse part
                    response_parts = []
                    for fn_call in function_calls:
                        fn_name = fn_call.get("name")
                        fn_args = fn_call.get("args", {})

                        logger.info(f"[LLM Tool Call Request] Tool: {fn_name}, Args: {fn_args}")
                        print(f"🔧 [Tool Call] Gemini가 Tool '{fn_name}' 호출을 요청했습니다 (인자: {fn_args})")

                        tool_result = self.dispatcher.dispatch(fn_name, fn_args)
                        print(f"📊 [Tool Result] {tool_result}")

                        response_parts.append({
                            "functionResponse": {
                                "name": fn_name,
                                "response": tool_result
                            }
                        })

                    # Append model turn and functionResponse turn to conversation
                    contents.append({
                        "role": "model",
                        "parts": parts
                    })
                    contents.append({
                        "role": "user",
                        "parts": response_parts
                    })
                    payload["contents"] = contents
                    continue

                if text_part is not None:
                    answer = text_part.strip()
                    # 대화 기억 저장: 사용자 질문 + 최종 답변만 (tool 중간 턴 제외)
                    self._history.append({"role": "user", "parts": [{"text": prompt}]})
                    self._history.append({"role": "model", "parts": [{"text": answer}]})
                    if len(self._history) > LLM_HISTORY_MAX_MESSAGES:
                        self._history = self._history[-LLM_HISTORY_MAX_MESSAGES:]
                    return answer

                return "응답 내용을 찾을 수 없습니다."

            except requests.exceptions.RequestException as e:
                logger.error(f"[GMS Client Error] HTTP 요청 실패: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.error(f"[GMS Client Error] Detailed response: {e.response.text}")
                return "LLM 응답을 가져오는 중 오류가 발생했습니다."

        return "Tool 호출 반복 횟수를 초과했습니다."
