# movensis LLM Interface

모델: Qwen2.5-7B LoRA
ROS2 Action Server로 전달

## 구조

```
model/
  chat.py                          # 대화형 메인 인터페이스
  qwen-robot/                      # LoRA 어댑터 (tokenizer 설정)
ros2_ws/src/robot_interfaces/
  robot_action_server.py           # ROS2 Action Server
  ros2_bridge.py                   # chat.py → ROS2 연결 브릿지
  action/RobotCommand.action       # Action 인터페이스 정의
  CMakeLists.txt / package.xml
```

## 실행 방법

### 1. 환경 설정

```bash
conda env create -f environment.yml
conda activate movensis-llm
```

### 2. ROS2 패키지 빌드

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build
source install/setup.bash
```

### 3. Action 서버 실행 (터미널 1)

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
python3 ros2_ws/src/robot_interfaces/robot_action_server.py
```

### 4. 대화형 인터페이스 실행 (터미널 2)

```bash
source /opt/ros/humble/setup.bash
source ros2_ws/install/setup.bash
python3 model/chat.py
```

## 동작 흐름

```
사용자 입력 (한국어)
    ↓
입력 분류 (Ollama qwen2.5:7b)
    ├─ 일반 대화 → 한국어 응답 반환
    └─ 로봇 명령 → LoRA 모델이 JSON 배열로 변환
                        ↓
                 사용자 확인 / 수정
                        ↓
                 ros2_bridge → ROS2 Action Server
                        ↓
                    로봇 실행
```

## 사용 가능한 로봇 명령

| 함수 | 설명 |
|------|------|
| `navigate_to('A')` | 구역 이동 (A~F) |
| `move_forward(2.0)` | 앞으로 이동 (미터) |
| `move_backward(1.5)` | 뒤로 이동 (미터) |
| `turn('left', 90)` | 회전 |
| `pick_up('cup')` | 물체 집기 |
| `put_down('cup')` | 물체 내려놓기 |
| `place_at('B')` | 특정 구역에 놓기 |
| `take_photo()` | 사진 촬영 |
| `record_video(30)` | 영상 녹화 (초) |
| `scan_area()` | 360도 스캔 |
| `detect_object('cup')` | 물체 탐지 |
| `return_to_base()` | 기지 복귀 |
| `stop()` | 긴급 정지 |
| `wait(5)` | 대기 (초) |
| `report_status()` | 상태 보고 |
| `charge()` | 충전 |

## 의존성

- Python 3.10+
- ROS2 (Humble 이상)
- Ollama (`qwen2.5:7b` 모델 필요)
- PyTorch, transformers, peft, bitsandbytes
- LoRA 가중치: [sugarpepper99/qwen-robot-lora](https://huggingface.co/sugarpepper99/qwen-robot-lora) (Hugging Face Hub에서 자동 다운로드)
