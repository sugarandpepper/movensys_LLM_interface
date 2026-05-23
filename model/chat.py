# model/chat.py
import json
import sys
import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
import ollama
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src', 'robot_interfaces'))
from ros2_bridge import send_to_robot_ros2, shutdown_ros

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
LORA_PATH  = "sugarpepper99/qwen-robot-lora"

SYSTEM_PROMPT = """당신은 로봇 제어 AI입니다.
사용자의 한국어 명령을 아래 함수 목록만 사용해 JSON 배열로 변환하세요.
다른 텍스트는 절대 출력하지 마세요. 반드시 JSON 배열만 출력하세요.

사용 가능한 함수:
navigate_to('A')       # 구역 이동 (A~F)
move_forward(2.0)      # 앞으로 이동 (미터)
move_backward(1.5)     # 뒤로 이동 (미터)
turn('left', 90)       # 회전
return_to_base()       # 기지 복귀
stop()                 # 정지
take_photo()           # 사진 촬영
record_video(30)       # 영상 녹화 (초)
scan_area()            # 360도 스캔
detect_object('cup')   # 물체 탐지
pick_up('cup')         # 물체 집기
put_down('cup')        # 물체 내려놓기
place_at('B')          # 특정 구역에 놓기
push('box')            # 물체 밀기
wait(5)                # 대기 (초)
report_status()        # 상태 보고
charge()               # 충전
"""

MODIFY_SYSTEM_PROMPT = """당신은 로봇 명령어 수정 AI입니다.
현재 명령어 배열과 사용자의 수정 요청을 받아 수정된 JSON 배열만 출력하세요.
다른 텍스트는 절대 출력하지 마세요. 반드시 JSON 배열만 출력하세요.

사용 가능한 함수:
navigate_to('A')       # 구역 이동 (A~F)
move_forward(2.0)      # 앞으로 이동 (미터)
move_backward(1.5)     # 뒤로 이동 (미터)
turn('left', 90)       # 회전
return_to_base()       # 기지 복귀
stop()                 # 정지
take_photo()           # 사진 촬영
record_video(30)       # 영상 녹화 (초)
scan_area()            # 360도 스캔
detect_object('cup')   # 물체 탐지
pick_up('cup')         # 물체 집기
put_down('cup')        # 물체 내려놓기
place_at('B')          # 특정 구역에 놓기
push('box')            # 물체 밀기
wait(5)                # 대기 (초)
report_status()        # 상태 보고
charge()               # 충전
"""

# ===================== 모델 로드 =====================
def load_model():
    print("모델 로드 중...")
    tokenizer = AutoTokenizer.from_pretrained(LORA_PATH, trust_remote_code=True)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base_model, LORA_PATH)
    model.eval()
    print("모델 로드 완료!\n")
    return model, tokenizer


# ===================== 추론 =====================
def generate(model, tokenizer, system: str, user: str) -> str:
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.1,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True
    ).strip()
    return response


def parse_commands(raw: str) -> list | None:
    try:
        # 코드블록 제거
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return None


# ===================== 명령 변환 =====================
def convert_to_commands(model, tokenizer, instruction: str) -> list | None:
    raw = generate(model, tokenizer, SYSTEM_PROMPT, instruction)
    return parse_commands(raw)


# ===================== 명령 수정 =====================
def modify_commands(model, tokenizer, current: list, request: str) -> list | None:
    user_msg = f"""현재 명령어 배열:
{json.dumps(current, ensure_ascii=False)}

수정 요청: {request}

수정된 JSON 배열만 출력하세요."""
    raw = generate(model, tokenizer, MODIFY_SYSTEM_PROMPT, user_msg)
    return parse_commands(raw)


# ===================== 명령어 출력 =====================
def print_commands(commands: list):
    print("\n┌─────────────────────────────────────")
    print("│ 실행 예정 명령어")
    print("├─────────────────────────────────────")
    for i, cmd in enumerate(commands, 1):
        print(f"│  {i}. {cmd}")
    print("└─────────────────────────────────────")


# ===================== 로봇 전송 =====================
def send_to_robot(commands: list):
    print("\n🤖 로봇에 명령 전송 중...")
    result = send_to_robot_ros2(commands)

    if result["success"]:
        print(f"✅ 완료: {result['message']}")
        print(f"   실행된 명령: {result['executed']}")
    else:
        print(f"❌ 실패: {result['message']}")
    print()

# ===================== 입력 분류 =====================
def classify_input(user_input: str) -> str:
    """로봇 명령인지 일반 대화인지 분류"""
    response = ollama.chat(
        model='qwen2.5:7b',
        messages=[
            {
                'role': 'system',
                'content': """사용자 입력이 로봇 제어 명령인지 일반 대화인지 분류하세요.
로봇 명령 예시: 'A구역 사진 찍어와', 'B구역으로 이동해', '박스 집어줘'
일반 대화 예시: '안녕', '잘 작동하네', '고마워', '뭘 할 수 있어?'

반드시 'robot' 또는 'chat' 중 하나만 출력하세요."""
            },
            {'role': 'user', 'content': user_input}
        ],
        options={'temperature': 0.1}
    )
    result = response['message']['content'].strip().lower()
    return 'robot' if 'robot' in result else 'chat'


# ===================== 일반 대화 =====================
def general_chat(user_input: str) -> str:
    """Ollama로 일반 대화 처리"""
    response = ollama.chat(
        model='qwen2.5:7b',
        messages=[
            {
                'role': 'system',
                'content': """당신은 로봇 제어 시스템의 AI 어시스턴트입니다.
반드시 한국어로만 대답하세요. 영어나 중국어로 절대 답하지 마세요.
절대로 중국어를 사용하지 마세요. 중국어 유니코드 범위에 있는 글자가 있으면 안 됩니다.
절대로 영어를 사용하지 마세요. 영어 유니코드 범위에 있는 글자가 있으면 안 됩니다.
친절하게 대화하되, 로봇 제어와 관련된 도움을 제공하세요.
로봇 명령을 내리고 싶으면 구체적인 동작을 말해달라고 안내하세요."""
            },
            {'role': 'user', 'content': user_input}
        ],
        options={'temperature': 0.7}
    )
    return response['message']['content'].strip()


# ===================== 메인 루프 =====================
def main():
    model, tokenizer = load_model()

    print("=" * 50)
    print("  로봇 제어 대화형 시스템")
    print("=" * 50)
    print("명령어를 입력하면 로봇 함수로 변환합니다.")
    print("종료하려면 'q' 또는 'quit'를 입력하세요.\n")

    while True:
        # 1. 명령 입력
        print("─" * 50)
        user_input = input("📝 명령 입력: ").strip()

        if user_input.lower() in ('q', 'quit', '종료'):
            print("시스템을 종료합니다.")
            shutdown_ros()
            break
        if not user_input:
            continue

       # 2. 입력 분류
        input_type = classify_input(user_input)

        if input_type == 'chat':
            # 일반 대화 처리
            reply = general_chat(user_input)
            print(f"\n🤖 {reply}\n")
            continue

        # 3. 함수 변환 (로봇 명령인 경우)
        print("\n⚙️  명령어 변환 중...")
        commands = convert_to_commands(model, tokenizer, user_input)

        if not commands:
            print("❌ 명령어 변환에 실패했습니다. 다시 입력해주세요.")
            continue

        # 3. 확인 루프
        while True:
            print_commands(commands)
            print("\n다음 중 선택하세요:")
            print("  [y] 확인 후 실행")
            print("  [n] 취소")
            print("  [수정 내용 직접 입력] 예: '2번이랑 3번 순서 바꿔줘' / '사진 촬영 빼줘'")

            choice = input("\n입력: ").strip()

            if choice.lower() in ('y', 'yes', '확인', '실행', '응', '네'):
                send_to_robot(commands)
                break

            elif choice.lower() in ('n', 'no', '취소', '아니', '아니오'):
                print("❌ 명령이 취소됐습니다.\n")
                break

            elif choice:
                # 수정 요청 처리
                print("\n⚙️  명령어 수정 중...")
                modified = modify_commands(model, tokenizer, commands, choice)
                if modified:
                    commands = modified
                    print("✅ 수정 완료!")
                else:
                    print("❌ 수정에 실패했습니다. 다시 입력해주세요.")


if __name__ == "__main__":
    main()