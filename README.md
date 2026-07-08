# movensys LLM Interface

모델: Qwen2.5-7B LoRA | 모바일 매니퓰레이터 한국어 자연어 제어 시스템

---

## 버전

| 버전 | 파일 | LoRA 가중치 | 명령어 |
|------|------|------------|--------|
| v1 | `model/chat.py` | [qwen-robot-lora](https://huggingface.co/sugarpepper99/qwen-robot-lora) | 17개 (구역이동, 촬영 등) |
| v2 | `model/chat_v2.py` | [qwen-robot-lora-v2](https://huggingface.co/sugarpepper99/qwen-robot-lora-v2) | 6개 (좌표 기반, 매니퓰레이터 제어) |

---

## 구조

```
model/
  chat.py                          # v1 대화형 인터페이스
  chat_v2.py                       # v2 대화형 인터페이스 (모바일 매니퓰레이터)
  finetune.py                      # v1 LoRA 파인튜닝
  finetune_v2.py                   # v2 LoRA 파인튜닝
  qwen-robot/                      # v1 LoRA 어댑터
  qwen-robot-v2/                   # v2 LoRA 어댑터
dataset/
  dataset.jsonl                    # v1 학습 데이터
  dataset_v2.jsonl                 # v2 학습 데이터
  generate_dataset.py              # v1 데이터 생성기 (Ollama)
  generate_dataset_v2.py           # v2 데이터 생성기 (Ollama)
  dataset_v2_prompt.txt            # v2 서버 LLM용 데이터 생성 프롬프트
ros2_ws/src/robot_interfaces/
  robot_action_server.py           # ROS2 Action Server
  ros2_bridge.py                   # chat.py → ROS2 연결 브릿지
  action/RobotCommand.action       # Action 인터페이스 정의
  CMakeLists.txt / package.xml
```

---

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

# v1 실행
python3 model/chat.py

# v2 실행 (모바일 매니퓰레이터)
python3 model/chat_v2.py
```

---

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
              [v2] 좌표 변환 처리
              move_base: body 프레임 → 글로벌 좌표
              move_ee:   delta → 절대 좌표
                        ↓
                 ros2_bridge → ROS2 Action Server
                        ↓
                    로봇 실행
```

---

## v2 로봇 명령어

모바일 베이스(3DOF)와 매니퓰레이터(6DOF)를 통합 제어합니다.

| 함수 | 설명 | 좌표계 |
|------|------|--------|
| `go(x, y, theta)` | 모바일 베이스 절대 좌표 이동 | 글로벌 |
| `go('zone')` | 구역('A'~'D')으로 이동 | - |
| `move_base(dx, dy, dyaw)` | 베이스 소량 이동 (body 프레임 delta → 글로벌 자동 변환) | body→글로벌 |
| `move_ee(dx, dy, dz, dr, dp, dyaw)` | 엔드이펙터 소량 이동 | 베이스 기준 |
| `pick(object)` | 물체 집기 | - |
| `open_gripper()` | 그리퍼 열기 | - |
| `detect(object)` | 물체 탐지 | - |

### 좌표 방향 기준

```
move_base: +dx=앞, +dy=왼쪽, +dyaw=반시계 (body 프레임)
move_ee:   +dx=오른쪽, +dy=앞, +dz=위 (베이스 프레임)
```

### move_base 좌표 변환 예시

현재 로봇 위치 (4, 3, 30°) 에서 오른쪽 1m 이동:
```
입력:  move_base(0, -1, 0)
변환:  global_dx = 0·cos30° - (-1)·sin30° = 0.5
       global_dy = 0·sin30° + (-1)·cos30° = -0.866
출력:  목표 좌표 (4.5, 2.134, 0.524)
```

---

## v1 로봇 명령어

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

---

## HuggingFace

| 종류 | 링크 |
|------|------|
| v1 모델 | [sugarpepper99/qwen-robot-lora](https://huggingface.co/sugarpepper99/qwen-robot-lora) |
| v2 모델 | [sugarpepper99/qwen-robot-lora-v2](https://huggingface.co/sugarpepper99/qwen-robot-lora-v2) |
| v2 데이터셋 | [sugarpepper99/qwen-robot-dataset-v2](https://huggingface.co/datasets/sugarpepper99/qwen-robot-dataset-v2) |

---

## 의존성

- Python 3.10+
- ROS2 Humble 이상
- Ollama (`qwen2.5:7b` 모델 필요)
- PyTorch, transformers, peft, bitsandbytes
