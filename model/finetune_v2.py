# model/finetune_v2.py
import json
import os
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# ==================== 설정 ====================
MODEL_NAME = "Qwen/Qwen2.5-7B-Instruct"
_ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH  = os.path.join(_ROOT, "dataset", "dataset_v2.jsonl")
OUTPUT_DIR = os.path.join(_ROOT, "model", "qwen-robot-v2")
LOG_DIR    = os.path.join(_ROOT, "logs")

# chat.py의 SYSTEM_PROMPT와 반드시 동일하게 유지
SYSTEM_PROMPT = """당신은 모바일 매니퓰레이터 로봇 제어 AI입니다.
사용자의 한국어 명령을 아래 함수 목록만 사용해 JSON 배열로 변환하세요.
다른 텍스트는 절대 출력하지 마세요. 반드시 JSON 배열만 출력하세요.

사용 가능한 함수:
go(x, y, theta)                          # 모바일 베이스를 글로벌 좌표로 이동 (x, y: 미터, theta: 라디안)
go('zone')                               # 지정 구역으로 이동 ('A', 'B', 'C', 'D' 중 하나)
move_base(dx, dy, dyaw)                  # 모바일 베이스 소량 이동 (body 프레임 기준 delta)
move_ee(dx, dy, dz, dr, dp, dyaw)        # 매니퓰레이터 소량 이동 (로봇 베이스 프레임 기준 delta)
pick(object)                             # 지정 물체 집기
open_gripper()                           # 그리퍼 열기
detect(object)                           # 지정 물체 탐지

좌표 기준:
- go(x,y,theta): 글로벌 좌표계 기준 절대 좌표
- go('zone'): 구역 이름으로 이동, 반드시 따옴표 포함
- move_base: +dx=앞, +dy=왼쪽, +dyaw=반시계방향 (body 프레임 기준 delta, 단위: 미터/라디안)
- move_ee: +dx=오른쪽, +dy=앞, +dz=위 (로봇 베이스 프레임 기준 delta, 단위: 미터/라디안)
"""


# ==================== 데이터 로드 ====================
def load_dataset_from_jsonl(path: str) -> Dataset:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            text = f"""<|im_start|>system
{SYSTEM_PROMPT}<|im_end|>
<|im_start|>user
{item['instruction']}<|im_end|>
<|im_start|>assistant
{json.dumps(item['output'], ensure_ascii=False)}<|im_end|>"""
            data.append({"text": text})
    print(f"데이터 로드 완료: {len(data)}개")
    return Dataset.from_list(data)


# ==================== 모델 로드 ====================
def load_model_and_tokenizer():
    print("토크나이저 로드 중...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    tokenizer.pad_token    = tokenizer.eos_token
    tokenizer.padding_side = "right"

    print("모델 로드 중 (4bit 양자화)...")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False
    return model, tokenizer


# ==================== LoRA 설정 ====================
def apply_lora(model):
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


# ==================== 학습 ====================
def train():
    print("=" * 50)
    print("로봇 LLM 파인튜닝 시작 (v2)")
    print("=" * 50)

    dataset          = load_dataset_from_jsonl(DATA_PATH)
    model, tokenizer = load_model_and_tokenizer()
    model            = apply_lora(model)

    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        fp16=False,
        bf16=True,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        warmup_steps=3,
        lr_scheduler_type="cosine",
        report_to="none",
        max_length=512,
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        args=training_args,
        processing_class=tokenizer,
    )

    print("\n학습 시작...")
    trainer.train()

    print("\n모델 저장 중...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"저장 완료: {OUTPUT_DIR}")


if __name__ == "__main__":
    train()
