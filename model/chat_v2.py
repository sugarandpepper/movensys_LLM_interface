# model/chat.py
import json
import sys
import os
import re
import math
import threading
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
import ollama

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src', 'robot_interfaces'))
from ros2_bridge import send_to_robot_ros2, shutdown_ros

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
LORA_PATH  = LORA_PATH = "sugarpepper99/qwen-robot-lora-v2"

# ROS2 토픽 이름 — 확정 시 수정
TOPIC_BASE_POSE = "/robot/base_pose"   # geometry_msgs/Pose2D: 글로벌 기준 모바일 베이스 (x, y, theta)
TOPIC_EE_POSE   = "/robot/ee_pose"    # geometry_msgs/Pose:  로봇 베이스 기준 엔드이펙터 (position + quaternion)

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

MODIFY_SYSTEM_PROMPT = """당신은 로봇 명령어 수정 AI입니다.
현재 명령어 배열과 사용자의 수정 요청을 받아 수정된 JSON 배열만 출력하세요.
다른 텍스트는 절대 출력하지 마세요. 반드시 JSON 배열만 출력하세요.

사용 가능한 함수:
go(x, y, theta) 또는 go('zone')
move_base(dx, dy, dyaw)
move_ee(dx, dy, dz, dr, dp, dyaw)
pick(object)
open_gripper()
detect(object)
"""


# ===================== 로봇 상태 캐시 =====================
class RobotStateCache:
    """ROS2 토픽을 구독해 최신 로봇 상태를 백그라운드에서 캐싱"""

    def __init__(self):
        self._base = {"x": 0.0, "y": 0.0, "theta": 0.0}
        self._ee   = {"x": 0.0, "y": 0.0, "z": 0.0,
                      "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._lock = threading.Lock()

    def update_base(self, x: float, y: float, theta: float):
        with self._lock:
            self._base = {"x": x, "y": y, "theta": theta}

    def update_ee(self, x: float, y: float, z: float,
                  roll: float, pitch: float, yaw: float):
        with self._lock:
            self._ee = {"x": x, "y": y, "z": z,
                        "roll": roll, "pitch": pitch, "yaw": yaw}

    def get(self) -> dict:
        with self._lock:
            return {"base": dict(self._base), "ee": dict(self._ee)}

    def start_subscriber(self):
        """ROS2 토픽 구독 시작 (백그라운드 데몬 스레드)
        토픽 확정 후 메시지 타입 및 필드명 맞춰 수정"""
        def _quat_to_rpy(qx, qy, qz, qw):
            roll  = math.atan2(2*(qw*qx + qy*qz), 1 - 2*(qx**2 + qy**2))
            pitch = math.asin(max(-1, min(1, 2*(qw*qy - qz*qx))))
            yaw   = math.atan2(2*(qw*qz + qx*qy), 1 - 2*(qy**2 + qz**2))
            return roll, pitch, yaw

        def _spin():
            try:
                import rclpy
                from geometry_msgs.msg import Pose2D, Pose

                node = rclpy.create_node("robot_state_cache")
                node.create_subscription(
                    Pose2D, TOPIC_BASE_POSE,
                    lambda msg: self.update_base(msg.x, msg.y, msg.theta),
                    10
                )

                def _ee_cb(msg):
                    r, p, y = _quat_to_rpy(
                        msg.orientation.x, msg.orientation.y,
                        msg.orientation.z, msg.orientation.w
                    )
                    self.update_ee(msg.position.x, msg.position.y,
                                   msg.position.z, r, p, y)

                node.create_subscription(Pose, TOPIC_EE_POSE, _ee_cb, 10)
                rclpy.spin(node)
            except Exception as e:
                print(f"[RobotStateCache] ROS2 구독 실패: {e}")

        threading.Thread(target=_spin, daemon=True).start()
        print(f"[RobotStateCache] 구독 시작\n  base: {TOPIC_BASE_POSE}\n  ee:   {TOPIC_EE_POSE}")


robot_state = RobotStateCache()


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
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return None


# ===================== 좌표 해석 =====================
def resolve_move_base(cmd: str) -> str:
    """move_base(dx, dy, dyaw) body 프레임 delta → 글로벌 절대 좌표로 변환"""
    m = re.search(r'move_base\(([^)]+)\)', cmd)
    if not m:
        return cmd

    vals = [float(v.strip()) for v in m.group(1).split(',')]
    if len(vals) != 3:
        return cmd

    dx, dy, dyaw = vals
    state  = robot_state.get()
    theta  = state["base"]["theta"]

    # body 프레임 → 글로벌 프레임
    global_dx = dx * math.cos(theta) - dy * math.sin(theta)
    global_dy = dx * math.sin(theta) + dy * math.cos(theta)

    target_x     = state["base"]["x"]     + global_dx
    target_y     = state["base"]["y"]     + global_dy
    target_theta = state["base"]["theta"] + dyaw

    return f"move_base({target_x:.4f}, {target_y:.4f}, {target_theta:.4f})"


def resolve_move_ee(cmd: str) -> str:
    """move_ee(dx,dy,dz,dr,dp,dyaw) delta → 현재 ee 상태에 더해 절대 좌표로 변환"""
    m = re.search(r'move_ee\(([^)]+)\)', cmd)
    if not m:
        return cmd

    vals = [float(v.strip()) for v in m.group(1).split(',')]
    if len(vals) != 6:
        return cmd

    dx, dy, dz, dr, dp, dyaw = vals
    ee = robot_state.get()["ee"]

    return (f"move_ee("
            f"{ee['x']+dx:.4f}, {ee['y']+dy:.4f}, {ee['z']+dz:.4f}, "
            f"{ee['roll']+dr:.4f}, {ee['pitch']+dp:.4f}, {ee['yaw']+dyaw:.4f})")


def resolve_commands(commands: list) -> list:
    resolved = []
    for cmd in commands:
        if cmd.startswith("move_base"):
            resolved.append(resolve_move_base(cmd))
        elif cmd.startswith("move_ee"):
            resolved.append(resolve_move_ee(cmd))
        else:
            resolved.append(cmd)
    return resolved


# ===================== 명령 변환 =====================
def convert_to_commands(model, tokenizer, instruction: str) -> list | None:
    raw = generate(model, tokenizer, SYSTEM_PROMPT, instruction)
    commands = parse_commands(raw)
    if commands:
        commands = resolve_commands(commands)
    return commands


# ===================== 명령 수정 =====================
def modify_commands(model, tokenizer, current: list, request: str) -> list | None:
    user_msg = f"""현재 명령어 배열:
{json.dumps(current, ensure_ascii=False)}

수정 요청: {request}

수정된 JSON 배열만 출력하세요."""
    raw = generate(model, tokenizer, MODIFY_SYSTEM_PROMPT, user_msg)
    commands = parse_commands(raw)
    if commands:
        commands = resolve_commands(commands)
    return commands


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
        if result.get("status_report"):
            print(f"\n📊 로봇 상태 보고\n   {result['status_report']}")
    else:
        print(f"❌ 실패: {result['message']}")
    print()


# ===================== 입력 분류 =====================
def classify_input(user_input: str) -> str:
    response = ollama.chat(
        model='qwen2.5:7b',
        messages=[
            {
                'role': 'system',
                'content': """사용자 입력이 로봇 제어 명령인지 일반 대화인지 분류하세요.
로봇 명령 예시: '좌표로 이동해', '물체 집어줘', '그리퍼 열어', '오른쪽으로 3cm 움직여', '컵 탐지해줘'
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
    response = ollama.chat(
        model='qwen2.5:7b',
        messages=[
            {
                'role': 'system',
                'content': """당신은 로봇 제어 시스템의 AI 어시스턴트입니다.
반드시 한국어로만 대답하세요. 영어나 중국어로 절대 답하지 마세요.
친절하게 대화하되, 로봇 제어와 관련된 도움을 제공하세요."""
            },
            {'role': 'user', 'content': user_input}
        ],
        options={'temperature': 0.7}
    )
    return response['message']['content'].strip()


# ===================== 메인 루프 =====================
def main():
    model, tokenizer = load_model()
    robot_state.start_subscriber()

    print("=" * 50)
    print("  모바일 매니퓰레이터 제어 시스템 v2")
    print("=" * 50)
    print("명령어를 입력하면 로봇 함수로 변환합니다.")
    print("종료하려면 'q' 또는 'quit'를 입력하세요.\n")

    while True:
        print("─" * 50)
        user_input = input("📝 명령 입력: ").strip()

        if user_input.lower() in ('q', 'quit', '종료'):
            print("시스템을 종료합니다.")
            shutdown_ros()
            break
        if not user_input:
            continue

        input_type = classify_input(user_input)

        if input_type == 'chat':
            reply = general_chat(user_input)
            print(f"\n🤖 {reply}\n")
            continue

        print("\n⚙️  명령어 변환 중...")
        commands = convert_to_commands(model, tokenizer, user_input)

        if not commands:
            print("❌ 명령어 변환에 실패했습니다. 다시 입력해주세요.")
            continue

        while True:
            print_commands(commands)
            print("\n다음 중 선택하세요:")
            print("  [y] 확인 후 실행")
            print("  [n] 취소")
            print("  [수정 내용 직접 입력] 예: '2번이랑 3번 순서 바꿔줘'")

            choice = input("\n입력: ").strip()

            if choice.lower() in ('y', 'yes', '확인', '실행', '응', '네'):
                send_to_robot(commands)
                break
            elif choice.lower() in ('n', 'no', '취소', '아니', '아니오'):
                print("❌ 명령이 취소됐습니다.\n")
                break
            elif choice:
                print("\n⚙️  명령어 수정 중...")
                modified = modify_commands(model, tokenizer, commands, choice)
                if modified:
                    commands = modified
                    print("✅ 수정 완료!")
                else:
                    print("❌ 수정에 실패했습니다. 다시 입력해주세요.")


if __name__ == "__main__":
    main()
