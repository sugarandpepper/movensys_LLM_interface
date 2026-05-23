# robot_action_server.py
import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from robot_interfaces.action import RobotCommand
import re


class RobotActionServer(Node):
    def __init__(self):
        super().__init__('robot_action_server')
        self._server = ActionServer(
            self,
            RobotCommand,
            'execute_robot_command',
            self._execute_callback
        )
        self.get_logger().info("✅ 로봇 Action 서버 시작")

    async def _execute_callback(self, goal_handle):
        commands = goal_handle.request.commands
        session_id = goal_handle.request.session_id
        executed = []
        feedback = RobotCommand.Feedback()

        self.get_logger().info(f"명령 수신 [{session_id}]: {commands}")

        for i, cmd in enumerate(commands):
            # 피드백 전송
            feedback.current_index = i
            feedback.current_command = cmd
            feedback.status = "실행 중"
            goal_handle.publish_feedback(feedback)

            # 명령 실행
            success = self._execute_command(cmd)

            if success:
                executed.append(cmd)
                feedback.status = "완료"
                goal_handle.publish_feedback(feedback)
            else:
                goal_handle.succeed()
                result = RobotCommand.Result()
                result.success = False
                result.message = f"명령 실패: {cmd}"
                result.executed = executed
                return result

        goal_handle.succeed()
        result = RobotCommand.Result()
        result.success = True
        result.message = f"전체 {len(executed)}개 명령 완료"
        result.executed = executed
        return result

    def _execute_command(self, cmd: str) -> bool:
        """실제 로봇 드라이버 호출 - 하드웨어 연결 시 여기에 코드 추가"""
        try:
            if cmd.startswith("navigate_to"):
                zone = re.search(r"'([A-F])'", cmd).group(1)
                self.get_logger().info(f"🚗 이동: {zone}구역")
                # TODO: Nav2 호출
                return True

            elif cmd.startswith("move_forward"):
                distance = re.search(r"([\d.]+)", cmd).group(1)
                self.get_logger().info(f"⬆️  앞으로 {distance}m 이동")
                # TODO: 모터 제어
                return True

            elif cmd.startswith("move_backward"):
                distance = re.search(r"([\d.]+)", cmd).group(1)
                self.get_logger().info(f"⬇️  뒤로 {distance}m 이동")
                # TODO: 모터 제어
                return True

            elif cmd.startswith("turn"):
                direction = re.search(r"'(\w+)'", cmd).group(1)
                angle = re.search(r",\s*(\d+)", cmd).group(1)
                self.get_logger().info(f"🔄 {direction}으로 {angle}도 회전")
                # TODO: 모터 제어
                return True

            elif cmd.startswith("take_photo"):
                self.get_logger().info("📷 사진 촬영")
                # TODO: 카메라 서비스 호출
                return True

            elif cmd.startswith("record_video"):
                duration = re.search(r"(\d+)", cmd).group(1)
                self.get_logger().info(f"🎥 영상 {duration}초 녹화")
                # TODO: 카메라 서비스 호출
                return True

            elif cmd.startswith("scan_area"):
                self.get_logger().info("🔍 360도 스캔")
                # TODO: 라이다/카메라 스캔
                return True

            elif cmd.startswith("detect_object"):
                obj = re.search(r"'(\w+)'", cmd).group(1)
                self.get_logger().info(f"🔎 물체 탐지: {obj}")
                # TODO: 비전 서비스 호출
                return True

            elif cmd.startswith("pick_up"):
                obj = re.search(r"'(\w+)'", cmd).group(1)
                self.get_logger().info(f"🦾 집기: {obj}")
                # TODO: 매니퓰레이터 제어
                return True

            elif cmd.startswith("put_down"):
                obj = re.search(r"'(\w+)'", cmd).group(1)
                self.get_logger().info(f"🦾 내려놓기: {obj}")
                # TODO: 매니퓰레이터 제어
                return True

            elif cmd.startswith("place_at"):
                zone = re.search(r"'([A-F])'", cmd).group(1)
                self.get_logger().info(f"📦 {zone}구역에 놓기")
                # TODO: Nav2 + 매니퓰레이터
                return True

            elif cmd.startswith("push"):
                obj = re.search(r"'(\w+)'", cmd).group(1)
                self.get_logger().info(f"👊 밀기: {obj}")
                # TODO: 매니퓰레이터 제어
                return True

            elif cmd.startswith("return_to_base"):
                self.get_logger().info("🏠 기지 복귀")
                # TODO: Nav2 홈 포지션
                return True

            elif cmd.startswith("stop"):
                self.get_logger().info("🛑 긴급 정지")
                # TODO: 모터 전체 정지
                return True

            elif cmd.startswith("wait"):
                seconds = re.search(r"(\d+)", cmd).group(1)
                self.get_logger().info(f"⏳ {seconds}초 대기")
                import time
                time.sleep(int(seconds))
                return True

            elif cmd.startswith("report_status"):
                self.get_logger().info("📊 상태 보고")
                # TODO: 센서 데이터 수집 및 보고
                return True

            elif cmd.startswith("charge"):
                self.get_logger().info("🔋 충전 시작")
                # TODO: 충전 스테이션 이동
                return True

            else:
                self.get_logger().warn(f"⚠️  알 수 없는 명령: {cmd}")
                return False

        except Exception as e:
            self.get_logger().error(f"명령 실행 오류 [{cmd}]: {e}")
            return False


def main():
    rclpy.init()
    server = RobotActionServer()
    try:
        rclpy.spin(server)
    except KeyboardInterrupt:
        pass
    finally:
        server.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()