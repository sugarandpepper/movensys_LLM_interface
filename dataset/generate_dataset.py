# dataset/generate_dataset.py
import ollama
import json
import time

FUNCTIONS = [
    "navigate_to(zone)",        # zone: 'A'~'F' 문자열
    "move_forward(distance)",   # distance: float (미터)
    "move_backward(distance)",  # distance: float (미터)
    "turn(direction, angle)",   # direction: 'left'/'right', angle: int (도)
    "return_to_base()",
    "stop()",
    "take_photo()",
    "record_video(duration)",   # duration: int (초)
    "scan_area()",
    "detect_object(object)",    # object: 영어 소문자 문자열
    "pick_up(object)",          # object: 영어 소문자 문자열
    "put_down(object)",         # object: 영어 소문자 문자열
    "place_at(zone)",           # zone: 'A'~'F' 문자열
    "push(object)",             # object: 영어 소문자 문자열
    "wait(seconds)",            # seconds: int
    "report_status()",
    "charge()",
]

SYSTEM_PROMPT = """당신은 로봇 제어용 학습 데이터를 생성하는 AI입니다.

[사용 가능한 함수 목록]
navigate_to('A')              # 구역 이동, zone은 반드시 'A'~'F' 중 하나
move_forward(2.0)             # 앞으로 이동, distance는 float
move_backward(1.5)            # 뒤로 이동, distance는 float
turn('left', 90)              # 회전, direction은 'left'/'right', angle은 int
return_to_base()              # 기지 복귀
stop()                        # 정지
take_photo()                  # 사진 촬영
record_video(30)              # 영상 녹화, duration은 int(초)
scan_area()                   # 360도 스캔
detect_object('cup')          # 물체 탐지, object는 반드시 영어 소문자
pick_up('cup')                # 물체 집기, object는 반드시 영어 소문자
put_down('cup')               # 물체 내려놓기, object는 반드시 영어 소문자
place_at('B')                 # 특정 구역에 놓기, zone은 반드시 'A'~'F' 중 하나
push('box')                   # 물체 밀기, object는 반드시 영어 소문자
wait(5)                       # 대기, seconds는 int
report_status()               # 상태 보고
charge()                      # 충전

[절대 규칙]
1. 출력은 반드시 JSON 한 줄만, 다른 텍스트 금지
2. 형식: {"instruction": "한국어 명령", "output": ["함수1", "함수2", ...]}
3. 함수 표기는 위 예시와 완전히 동일한 형식 사용
4. object 파라미터는 반드시 영어 소문자 (cup, box, book, bottle 등)
5. zone 파라미터는 반드시 따옴표 포함 ('A', 'B', 'C', 'D', 'E', 'F')
6. instruction은 반드시 한국어만 사용 (중국어, 영어 혼입 금지)
7. 함수 순서는 반드시 논리적 순서 (이동 후 촬영, 이동 후 집기 등)
8. navigate_to 없이 pick_up, take_photo 등 사용 금지 (이미 해당 구역에 있는 경우 제외)

[올바른 예시]
{"instruction": "A구역으로 이동해서 사진 찍어와", "output": ["navigate_to('A')", "take_photo()"]}
{"instruction": "B구역 박스를 C구역으로 옮겨줘", "output": ["navigate_to('B')", "pick_up('box')", "navigate_to('C')", "put_down('box')"]}
{"instruction": "D구역에서 30초 영상 녹화하고 복귀해", "output": ["navigate_to('D')", "record_video(30)", "return_to_base()"]}

[틀린 예시 - 절대 사용 금지]
navigate_to(A)          ← 따옴표 없음
navigate_to(zone='A')   ← 파라미터명 포함
pick_up(커피잔)          ← 한국어 object
take_photo              ← 괄호 없음
record_video            ← 파라미터 없음
"""

SCENARIOS = [
    ("이동+촬영", "특정 구역으로 이동해서 사진을 찍는 단순한 명령. navigate_to + take_photo 조합."),
    ("이동+운반", "한 구역의 물체를 집어서 다른 구역으로 옮기는 명령. pick_up + navigate_to + put_down 조합."),
    ("탐색+촬영", "물체를 탐지하거나 스캔한 후 사진을 찍는 명령. detect_object 또는 scan_area + take_photo 조합."),
    ("정찰+보고", "구역을 스캔하고 상태를 보고하는 명령. scan_area + report_status 조합."),
    ("긴급정지+복귀", "즉시 정지하거나 기지로 복귀하는 명령. stop 또는 return_to_base 포함."),
    ("복합임무", "이동+촬영+집기+복귀 등 3단계 이상의 복합 명령."),
    ("녹화임무", "특정 구역으로 이동해서 영상을 녹화하는 명령. record_video 포함."),
    ("회전+이동", "방향 전환 후 이동하는 명령. turn + move_forward 또는 navigate_to 조합."),
]

OBJECT_LIST = [
    "cup", "box", "book", "bottle", "ball", "bag", "chair", "table",
    "plant", "lamp", "phone", "laptop", "pen", "notebook", "umbrella",
    "basket", "stone", "card", "key", "tool"
]

def generate_sample(scenario_name: str, scenario_desc: str, index: int) -> dict | None:
    prompt = f"""시나리오: {scenario_name}
설명: {scenario_desc}
사용할 물체(필요시): {OBJECT_LIST[index % len(OBJECT_LIST)]}
샘플 번호: {index} (다양한 표현과 구역 사용)

위 조건에 맞는 데이터 1개를 JSON 한 줄로 출력하세요."""

    try:
        response = ollama.chat(
            model='qwen2.5:7b',
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt}
            ],
            options={'temperature': 0.8}
        )
        raw = response['message']['content'].strip()

        # 코드블록 제거
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        # JSON 한 줄만 추출
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("{"):
                raw = line
                break

        data = json.loads(raw)

        # 유효성 검사
        assert "instruction" in data, "instruction 없음"
        assert "output" in data, "output 없음"
        assert isinstance(data["output"], list), "output이 리스트가 아님"
        assert len(data["output"]) >= 1, "output이 비어있음"

        # 함수 형식 검사
        for func in data["output"]:
            assert "(" in func and ")" in func, f"괄호 없음: {func}"
            assert not any(k in func for k in ["zone=", "zone:", "object=", "object:", "direction=", "distance="]), \
                f"파라미터명 포함: {func}"

        # 한국어 instruction 검사 (중국어 유니코드 범위 감지)
        for ch in data["instruction"]:
            assert not ('\u4e00' <= ch <= '\u9fff'), f"중국어 포함: {data['instruction']}"

        return data

    except Exception as e:
        print(f"  [오류] 샘플 {index} 실패: {e}")
        return None


def generate_dataset(total: int = 300):
    dataset = []
    failed = 0

    print(f"총 {total}개 데이터 생성 시작...\n")

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

    # 저장
    output_path = "/home/woojin/movensis/Mobile_LLM/dataset/dataset.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n✅ 완료! 성공: {len(dataset)}개 / 실패: {failed}개")
    print(f"저장 위치: {output_path}")


if __name__ == "__main__":
    generate_dataset(total=300)