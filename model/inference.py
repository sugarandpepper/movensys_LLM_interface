# model/inference.py
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
LORA_PATH  = "/home/woojin/movensis/Mobile_LLM/model/qwen-robot"

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


def predict(model, tokenizer, instruction: str) -> list:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": instruction},
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
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

    try:
        commands = json.loads(response)
        return commands
    except json.JSONDecodeError:
        return [f"파싱 오류: {response}"]


def main():
    model, tokenizer = load_model()

    # 테스트 명령어 목록
    test_cases = [
        "A구역에 있는 물컵의 사진을 찍어와",
        "B구역 박스를 C구역으로 옮겨줘",
        "D구역을 스캔하고 상태 보고해",
        "즉시 정지하고 기지로 복귀해",
        "E구역으로 이동해서 30초 동안 영상 녹화하고 복귀해",
    ]

    print("=" * 50)
    print("파인튜닝 모델 테스트")
    print("=" * 50)

    for instruction in test_cases:
        print(f"\n입력: {instruction}")
        commands = predict(model, tokenizer, instruction)
        print(f"출력: {commands}")

    # 대화형 테스트
    print("\n" + "=" * 50)
    print("직접 입력 테스트 (종료: 'q')")
    print("=" * 50)
    while True:
        user_input = input("\n명령 입력: ").strip()
        if user_input.lower() == 'q':
            break
        if user_input:
            commands = predict(model, tokenizer, user_input)
            print(f"출력: {commands}")


if __name__ == "__main__":
    main()