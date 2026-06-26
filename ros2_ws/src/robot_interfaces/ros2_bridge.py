# ros2_bridge.py
try:
    import rclpy
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from rclpy.executors import SingleThreadedExecutor
    from robot_interfaces.action import RobotCommand
    import threading
    import uuid
    _ROS_AVAILABLE = True
except Exception:
    # 테스트/개발 환경: ROS2 메시지 타입 또는 rclpy가 없을 수 있음
    _ROS_AVAILABLE = False
    import threading
    import uuid


class RobotActionClient(Node):
    def __init__(self):
        super().__init__('llm_robot_client')
        self._client = ActionClient(self, RobotCommand, 'execute_robot_command')
        self._result = None
        self._done_event = threading.Event()

    def send_commands(self, commands: list) -> dict:
        # Action 서버 대기
        if not self._client.wait_for_server(timeout_sec=5.0):
            return {"success": False, "message": "❌ 로봇 서버에 연결할 수 없습니다."}

        # Goal 생성
        goal = RobotCommand.Goal()
        goal.commands = commands
        goal.session_id = str(uuid.uuid4())[:8]

        self._done_event.clear()
        self._result = None

        # 전송
        send_goal_future = self._client.send_goal_async(
            goal,
            feedback_callback=self._feedback_callback
        )
        send_goal_future.add_done_callback(self._goal_response_callback)

        # 완료 대기 (최대 60초)
        self._done_event.wait(timeout=60.0)

        if self._result is None:
            return {"success": False, "message": "❌ 타임아웃: 로봇 응답 없음"}

        return {
            "success": self._result.success,
            "message": self._result.message,
            "executed": list(self._result.executed),
            "status_report": self._result.status_report
        }

    def _goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            print("❌ 명령이 거부됐습니다.")
            self._done_event.set()
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_callback)

    def _feedback_callback(self, feedback_msg):
        fb = feedback_msg.feedback
        print(f"   [{fb.current_index + 1}] {fb.current_command} → {fb.status}")

    def _result_callback(self, future):
        self._result = future.result().result
        self._done_event.set()


# 싱글톤으로 관리
_ros_initialized = False
_robot_client = None
_executor = None
_executor_thread = None


def init_ros():
    global _ros_initialized, _robot_client, _executor, _executor_thread
    if not _ros_initialized:
        if not _ROS_AVAILABLE:
            # ROS가 없으면 초기화 없이 빈 클라이언트를 사용
            _robot_client = None
            _ros_initialized = True
            print("⚠️ ROS2 모듈 미설치: 시뮬레이션 모드로 동작")
            return
        rclpy.init()
        _robot_client = RobotActionClient()
        _executor = SingleThreadedExecutor()
        _executor.add_node(_robot_client)
        _executor_thread = threading.Thread(target=_executor.spin, daemon=True)
        _executor_thread.start()
        _ros_initialized = True
        print("✅ ROS2 초기화 완료")


def send_to_robot_ros2(commands: list) -> dict:
    """chat.py에서 호출하는 메인 함수"""
    init_ros()
    if not _ROS_AVAILABLE or _robot_client is None:
        # 시뮬레이션: 즉시 성공 응답을 반환
        print(f"[SIM] Sending commands to simulated robot: {commands}")
        return {
            "success": True,
            "message": "시뮬레이션: 명령이 전송되었습니다",
            "executed": commands,
            "status_report": "battery:100% 위치:(5.0,5.0) 방향:0° 속도:0.0"
        }
    return _robot_client.send_commands(commands)


def shutdown_ros():
    global _ros_initialized
    if _ros_initialized:
        if _ROS_AVAILABLE:
            rclpy.shutdown()
        _ros_initialized = False