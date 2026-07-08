# dataset/generate_dataset_v2.py
import ollama
import json
import os
import time

FUNCTIONS = [
    "go(x, y, theta)",
    "go('zone')",
    "move_base(dx, dy, dyaw)",
    "move_ee(dx, dy, dz, dr, dp, dyaw)",
    "pick(object)",
    "open_gripper()",
    "detect(object)",
]

ZONES = ["A", "B", "C", "D"]

SYSTEM_PROMPT = """당신은 모바일 매니퓰레이터 로봇 제어용 학습 데이터를 생성하는 AI입니다.

[사용 가능한 함수]
go(x, y, theta)                          # 모바일 베이스를 글로벌 좌표로 이동 (x, y: 미터, theta: 라디안)
go('zone')                               # 지정 구역으로 이동 (zone: 'A'~'D' 중 하나)
move_base(dx, dy, dyaw)                  # 모바일 베이스 소량 이동 (body 프레임 기준 delta)
move_ee(dx, dy, dz, dr, dp, dyaw)        # 매니퓰레이터 소량 이동 (로봇 베이스 프레임 기준 delta)
pick(object)                             # 지정 물체 집기
open_gripper()                           # 그리퍼 열기
detect(object)                           # 지정 물체 탐지

[좌표 기준]
- go(x,y,theta): 글로벌 좌표계 절대 좌표 (x, y: 미터, theta: 라디안)
- go('zone'): 구역 이름으로 이동, 반드시 따옴표 포함 ('A', 'B', 'C', 'D')
- move_base: +dx=앞, +dy=왼쪽, +dyaw=반시계방향 (body 프레임 delta, 단위: 미터/라디안)
- move_ee: +dx=오른쪽, +dy=앞, +dz=위 (로봇 베이스 프레임 delta, 단위: 미터/라디안)
- move_base, move_ee 수치는 소량 이동 (보통 0.01~0.2m, 0.01~0.3rad)

[절대 규칙]
1. 출력은 반드시 JSON 한 줄만, 다른 텍스트 금지
2. 형식: {"instruction": "한국어 명령", "output": ["함수1", "함수2", ...]}
3. instruction은 반드시 한국어만 (중국어, 영어 혼입 금지)
4. object 파라미터는 반드시 영어 소문자 문자열 ('cup', 'box' 등)
5. zone 파라미터는 반드시 따옴표 포함 ('A', 'B', 'C', 'D')
6. 수치는 반드시 소수점 형식 사용

[올바른 예시]
{"instruction": "A구역으로 이동해", "output": ["go('A')"]}
{"instruction": "B구역으로 이동해서 컵 집어줘", "output": ["go('B')", "detect('cup')", "open_gripper()", "pick('cup')"]}
{"instruction": "C구역 이동 후 박스 탐지해", "output": ["go('C')", "detect('box')"]}
{"instruction": "좌표 (2.0, 1.5, 0.0)으로 이동해", "output": ["go(2.0, 1.5, 0.0)"]}
{"instruction": "앞으로 10cm만 이동해", "output": ["move_base(0.1, 0, 0)"]}
{"instruction": "오른쪽으로 5cm 이동해", "output": ["move_base(0, -0.05, 0)"]}
{"instruction": "그리퍼를 오른쪽으로 3cm 이동해", "output": ["move_ee(0.03, 0, 0, 0, 0, 0)"]}
{"instruction": "팔을 위로 5cm 올려줘", "output": ["move_ee(0, 0, 0.05, 0, 0, 0)"]}
{"instruction": "컵 탐지 후 집어줘", "output": ["detect('cup')", "open_gripper()", "pick('cup')"]}
{"instruction": "좌표 (3.0, -1.0, 1.57)로 이동해서 박스 탐지해", "output": ["go(3.0, -1.0, 1.57)", "detect('box')"]}

[틀린 예시 - 절대 사용 금지]
go(A)          ← 따옴표 없음
go(zone='A')   ← 파라미터명 포함
"""

SCENARIOS = [
    (
        "좌표이동",
        "특정 글로벌 좌표로 이동하는 단순 명령. go(x,y,theta) 함수만 사용. "
        "instruction에 좌표를 포함할 것. 예: '좌표 ({x}, {y}, {theta})로 이동해'"
    ),
    (
        "구역이동",
        "구역 이름으로 이동하는 명령. go('zone') 함수만 사용. "
        "구역은 A~D 중 하나. 예: 'A구역으로 이동해', 'B구역 가줘'"
    ),
    (
        "구역이동+탐지",
        "구역으로 이동한 후 물체를 탐지하는 명령. go('zone') + detect 조합. "
        "예: 'B구역으로 이동해서 컵 찾아줘'"
    ),
    (
        "구역이동+집기",
        "구역으로 이동 후 물체를 탐지하고 집는 명령. "
        "go('zone') + detect + open_gripper + pick 조합."
    ),
    (
        "좌표이동+탐지",
        "특정 좌표로 이동한 후 물체를 탐지하는 명령. go(x,y,theta) + detect 조합."
    ),
    (
        "베이스_소량이동",
        "모바일 베이스를 소량 이동시키는 명령. move_base만 사용. "
        "앞/뒤/왼쪽/오른쪽 이동 또는 소량 회전. 수치는 0.01~0.2m, 회전은 0.05~0.3rad."
    ),
    (
        "EE_소량이동",
        "매니퓰레이터 엔드이펙터를 소량 이동시키는 명령. move_ee만 사용. "
        "오른쪽/앞/위 방향 이동 또는 소량 회전. 수치는 0.01~0.1m."
    ),
    (
        "탐지+집기",
        "현재 위치에서 물체를 탐지하고 집는 명령 (이동 없음). "
        "detect + open_gripper + pick 조합."
    ),
    (
        "소량이동+집기",
        "베이스 또는 EE를 소량 조정한 뒤 물체를 집는 명령. "
        "move_base 또는 move_ee + pick 조합."
    ),
    (
        "복합임무",
        "이동 + EE 조정 + 탐지 + 집기 등 3단계 이상의 복합 명령. "
        "go('zone') 또는 go(x,y,theta) + move_ee + detect + pick 등 조합."
    ),
]

OBJECT_LIST = [
    "cup", "box", "book", "bottle", "ball",
    "bag", "phone", "pen", "tool", "key",
    "basket", "stone", "card", "cap", "block",
]

# 예시 좌표 (go 명령용)
COORD_PRESETS = [
    (1.0, 0.5, 0.0), (2.0, 1.5, 0.0), (3.0, -1.0, 1.57),
    (-1.5, 2.0, 3.14), (0.5, -0.5, -1.57), (4.0, 2.0, 0.785),
    (-2.0, -1.0, 0.0), (1.5, 3.0, 2.36), (2.5, 0.0, 1.0),
    (-0.5, 1.0, -0.5),
]


def generate_sample(scenario_name: str, scenario_desc: str, index: int) -> dict | None:
    obj   = OBJECT_LIST[index % len(OBJECT_LIST)]
    coord = COORD_PRESETS[index % len(COORD_PRESETS)]
    zone  = ZONES[index % len(ZONES)]
    desc  = scenario_desc.format(x=coord[0], y=coord[1], theta=coord[2])

    prompt = f"""시나리오: {scenario_name}
설명: {desc}
사용할 물체(필요시): {obj}
참고 좌표(필요시): go({coord[0]}, {coord[1]}, {coord[2]})
참고 구역(필요시): go('{zone}')
샘플 번호: {index} (다양한 표현 사용)

위 조건에 맞는 데이터 1개를 JSON 한 줄로 출력하세요."""

    try:
        response = ollama.chat(
            model='qwen2.5:7b',
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user',   'content': prompt}
            ],
            options={'temperature': 0.8}
        )
        raw = response['message']['content'].strip()

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("{"):
                raw = line
                break

        data = json.loads(raw)

        assert "instruction" in data
        assert "output" in data and isinstance(data["output"], list)
        assert len(data["output"]) >= 1

        valid_prefixes = ("go", "move_base", "move_ee", "pick", "open_gripper", "detect")
        for func in data["output"]:
            assert "(" in func and ")" in func, f"괄호 없음: {func}"
            assert any(func.startswith(p) for p in valid_prefixes), \
                f"허용되지 않은 함수: {func}"
            # go('zone') 형식이면 따옴표 확인
            if func.startswith("go(") and "'" in func:
                zone_val = func[4:-2]  # go('X') → X
                assert zone_val in ZONES, f"잘못된 구역: {zone_val}"

        for ch in data["instruction"]:
            assert not ('一' <= ch <= '鿿'), f"중국어 포함: {data['instruction']}"

        return data

    except Exception as e:
        print(f"  [오류] 샘플 {index} 실패: {e}")
        return None


def generate_dataset(total: int = 300):
    dataset = []
    failed  = 0

    print(f"총 {total}개 데이터 생성 시작 (v2)...\n")

    for i in range(total):
        scenario_name, scenario_desc = SCENARIOS[i % len(SCENARIOS)]
        print(f"[{i+1}/{total}] {scenario_name}")

        sample = generate_sample(scenario_name, scenario_desc, i)
        if sample:
            dataset.append(sample)
            print(f"  ✓ {sample['instruction']}")
            print(f"    → {sample['output']}")
        else:
            failed += 1

        time.sleep(0.2)

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset_v2.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n✅ 완료! 성공: {len(dataset)}개 / 실패: {failed}개")
    print(f"저장 위치: {output_path}")


if __name__ == "__main__":
    generate_dataset(total=300)
