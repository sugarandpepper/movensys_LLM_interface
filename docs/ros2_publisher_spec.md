# ROS2 로봇 상태 퍼블리셔 구현 명세

LLM 인터페이스(`chat_v2.py`)가 로봇의 현재 위치를 수신하기 위해
구독하고 있는 ROS2 토픽에 맞는 퍼블리셔 구현 사양입니다.

---

## 1. 구독자 측 현재 구현 (chat_v2.py 요약)

```python
# 토픽 이름
TOPIC_BASE_POSE = "/robot/base_pose"
TOPIC_EE_POSE   = "/robot/ee_pose"

# 베이스 구독
node.create_subscription(
    Pose2D,                                          # 메시지 타입
    "/robot/base_pose",
    lambda msg: update_base(msg.x, msg.y, msg.theta),
    10                                               # 큐 사이즈
)

# EE 구독 (quaternion → rpy 내부 변환)
node.create_subscription(
    Pose,                                            # 메시지 타입
    "/robot/ee_pose",
    callback,
    10
)
# EE 콜백에서 사용하는 필드:
#   msg.position.x, msg.position.y, msg.position.z
#   msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w
```

---

## 2. 퍼블리셔 구현 요구사항

### 토픽 1: 모바일 베이스 위치

| 항목 | 내용 |
|------|------|
| 토픽명 | `/robot/base_pose` |
| 메시지 타입 | `geometry_msgs/msg/Pose2D` |
| 좌표계 | **글로벌 좌표계 (map frame)** |
| 필드 | `x` (미터), `y` (미터), `theta` (라디안) |
| 권장 퍼블리시 주기 | 10~50 Hz |

```
x, y   : 글로벌 좌표계 기준 모바일 베이스의 위치 (미터)
theta  : 글로벌 좌표계 기준 모바일 베이스의 yaw 각도 (라디안)
         +theta = 반시계방향 (ROS 표준)
```

**일반적인 데이터 소스:**
- `nav_msgs/Odometry` 토픽 → x, y, quaternion → yaw 변환
- SLAM 결과 (`/amcl_pose`, `/odom` 등)
- 모바일 로봇 드라이버의 pose 토픽

---

### 토픽 2: 매니퓰레이터 엔드이펙터 위치

| 항목 | 내용 |
|------|------|
| 토픽명 | `/robot/ee_pose` |
| 메시지 타입 | `geometry_msgs/msg/Pose` |
| 좌표계 | **모바일 로봇 베이스 프레임 기준** |
| 필드 | `position` (xyz 미터), `orientation` (quaternion xyzw) |
| 권장 퍼블리시 주기 | 10~50 Hz |

```
position.x, y, z    : 모바일 베이스 기준 엔드이펙터 위치 (미터)
orientation.x, y, z, w : 엔드이펙터 자세 (quaternion)
                         chat_v2.py 내부에서 rpy로 자동 변환됨
```

**일반적인 데이터 소스:**
- `robot_state_publisher` + `tf2` → base_link 기준 ee_link transform
- 매니퓰레이터 드라이버의 end_effector_pose 토픽
- MoveIt의 `/move_group/monitored_planning_scene` 또는 FK 계산 결과

---

## 3. 구현 예시 (Python ROS2 노드)

```python
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose2D, Pose

class RobotStatePublisher(Node):
    def __init__(self):
        super().__init__('robot_state_publisher')

        self.base_pub = self.create_publisher(Pose2D, '/robot/base_pose', 10)
        self.ee_pub   = self.create_publisher(Pose,   '/robot/ee_pose',   10)

        self.create_timer(0.05, self.publish_state)  # 20Hz

    def publish_state(self):
        # ── 베이스 퍼블리시 ──────────────────────────────
        base_msg = Pose2D()
        base_msg.x     = ...  # 글로벌 x (미터)
        base_msg.y     = ...  # 글로벌 y (미터)
        base_msg.theta = ...  # 글로벌 yaw (라디안)
        self.base_pub.publish(base_msg)

        # ── EE 퍼블리시 ──────────────────────────────────
        ee_msg = Pose()
        ee_msg.position.x    = ...  # 베이스 기준 x (미터)
        ee_msg.position.y    = ...  # 베이스 기준 y (미터)
        ee_msg.position.z    = ...  # 베이스 기준 z (미터)
        ee_msg.orientation.x = ...  # quaternion x
        ee_msg.orientation.y = ...  # quaternion y
        ee_msg.orientation.z = ...  # quaternion z
        ee_msg.orientation.w = ...  # quaternion w
        self.ee_pub.publish(ee_msg)

def main():
    rclpy.init()
    node = RobotStatePublisher()
    rclpy.spin(node)
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

---

## 4. 좌표계 요약

```
[글로벌 좌표계]
  ↑ y
  │
  └──→ x       모바일 베이스 위치 (x, y, theta) 기준

[모바일 베이스 프레임]
  ↑ z
  │   ↗ y (앞)
  └──→ x (오른쪽)

  엔드이펙터 위치는 이 프레임 기준
```

---

## 5. 확인 방법

퍼블리셔 구현 후 아래 명령으로 토픽 수신 여부 확인:

```bash
ros2 topic echo /robot/base_pose
ros2 topic echo /robot/ee_pose
ros2 topic hz /robot/base_pose    # 퍼블리시 주기 확인
```

chat_v2.py 실행 후 `move_base` 또는 `move_ee` 명령 입력 시
실제 로봇 위치 기반으로 목표 좌표가 계산되면 정상 동작입니다.
