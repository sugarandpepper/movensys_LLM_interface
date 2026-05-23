# model/finetune.py
import json
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer, SFTConfig

# ==================== 설정 ====================
MODEL_NAME   = "Qwen/Qwen2.5-7B-Instruct"
DATA_PATH    = "/home/woojin/movensis/Mobile_LLM/dataset/dataset.jsonl"
OUTPUT_DIR   = "/home/woojin/movensis/Mobile_LLM/model/qwen-robot"
LOG_DIR      = "/home/woojin/movensis/Mobile_LLM/logs"

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

# ==================== 데이터 로드 ====================
def load_dataset_from_jsonl(path: str) -> Dataset:
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            # Qwen 채팅 템플릿 형식으로 변환
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
    tokenizer.pad_token = tokenizer.eos_token
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
    print("로봇 LLM 파인튜닝 시작")
    print("=" * 50)

    dataset  = load_dataset_from_jsonl(DATA_PATH)
    model, tokenizer = load_model_and_tokenizer()
    model    = apply_lora(model)

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