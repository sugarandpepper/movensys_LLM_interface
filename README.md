# MPC prototype (Python)

간단한 로컬 프로토타입: conda 환경 생성 후 FastAPI 서버를 실행하고 예제 템플릿으로 동작을 확인합니다.

환경 생성:

```bash
conda env create -f environment.yml
conda activate mpc-project
```


서버 실행 (터미널 1):

```bash
conda activate mpc-project
uvicorn mcp_server.server:app --reload
```

UI 실행 (터미널 2 — 입력창 역할):

```bash
python ui/cli_ui.py
```


이 프로젝트는 단일 템플릿 `MobileRobot_Sequence`를 기본으로 사용합니다. UI와 스크립트는 이 템플릿을 자동으로 참조합니다.

예제 사용법:
- 서버: 

```bash
uvicorn mcp_server.server:app --reload
```
- UI(REPL):

```bash
python ui/cli_ui.py
```

UI에서 `command`에 로봇 시퀀스를 지시하는 자유형 텍스트를 입력하고(예: "move forward 5m; turn left; pick up object"), `meta`에 추가 데이터가 필요하면 JSON으로 전달하세요 (`{"values":[...]]}` 등).

메모: 흐름 요약 — UI에서 입력 → 서버의 `/run_command` 호출 → (1) 템플릿에 선언된 MCP 연산이 있으면 `mcp_server.runner`가 연산을 시뮬레이션하여 결과를 `meta[\"mcp_results\"]`에 추가합니다. (2) `mcp_server.llm_client`가 LLM(또는 mock)을 호출해 템플릿에 맞는 JSON 아웃풋을 생성해 반환합니다.
