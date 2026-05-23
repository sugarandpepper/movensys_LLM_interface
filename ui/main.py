import sys
import json
from datetime import datetime
from pathlib import Path
import math
import requests
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QLabel, QTextEdit, QScrollArea
)
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QBrush, QPixmap
from PyQt5.QtWidgets import QFrame

# uvicorn mcp_server.server:app --reload
# 서버실행
# source /home/woojin/movensis/movensis/bin/activate

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FACTORY_IMAGE_PATH = PROJECT_ROOT / "image" / "factory.png"
OUTPUT_DIR = PROJECT_ROOT / "outputs"


class RectangleArea:
    """클릭 가능한 직사각형 영역 (픽셀 좌표 기반)"""
    def __init__(self, name, x1, y1, x2, y2, img_width, img_height):
        self.name = name  # 영역 이름
        self.x1 = x1  # 픽셀 좌표 (좌상단 x)
        self.y1 = y1  # 픽셀 좌표 (좌상단 y)
        self.x2 = x2  # 픽셀 좌표 (우하단 x)
        self.y2 = y2  # 픽셀 좌표 (우하단 y)
        self.img_width = img_width  # 원본 이미지 너비
        self.img_height = img_height  # 원본 이미지 높이
        self.selected = False  # 선택 상태

    def contains_image_point(self, img_pixel_x, img_pixel_y):
        """이미지 픽셀 좌표가 직사각형 내부에 있는지 확인"""
        return (self.x1 <= img_pixel_x <= self.x2 and
                self.y1 <= img_pixel_y <= self.y2)

    def toggle_selection(self):
        """선택 상태 토글"""
        self.selected = not self.selected
    
    def get_screen_coords(self, img_render_x, img_render_y, img_render_width, img_render_height, orig_img_width, orig_img_height):
        """이미지의 실제 렌더링 위치를 고려한 화면 좌표 반환"""
        # 원본 이미지 좌표를 렌더링 좌표로 변환
        scale_x = img_render_width / orig_img_width
        scale_y = img_render_height / orig_img_height
        
        x1_screen = int(img_render_x + self.x1 * scale_x)
        y1_screen = int(img_render_y + self.y1 * scale_y)
        x2_screen = int(img_render_x + self.x2 * scale_x)
        y2_screen = int(img_render_y + self.y2 * scale_y)
        return x1_screen, y1_screen, x2_screen, y2_screen


class MapCanvas(QFrame):
    """맵 캔버스 - 클릭으로 위치를 표시할 수 있는 영역"""

    MAP_WIDTH = 4
    MAP_HEIGHT = 3
    GRID_COLOR = QColor(200, 200, 200)
    GRID_WIDTH = 1
    CLICK_COLOR = QColor(255, 0, 0)  # 빨간색
    CLICK_RADIUS = 100  # 원의 반지름 (픽셀)
    ROBOT_COLOR = QColor(255, 0, 0)
    ROBOT_SIZE = 0.2
    ROBOT_X = 2.0  # 로봇 X 위치 (오른쪽)
    ROBOT_Y = 1.5  # 로봇 Y 위치 (중앙)
    
    # 직사각형 관련 색상
    RECT_NORMAL_COLOR = QColor(100, 100, 255, 0)  # 기본은 투명 (선택 안 됨)
    RECT_SELECTED_COLOR = QColor(255, 100, 100)  # 선택된 빨간색
    RECT_BORDER_COLOR = QColor(255, 0, 0)  # 빨간색 테두리 (선택 시)

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: white; border: 1px solid black;")
        self.setMinimumSize(600, 450)

        # 배경 이미지 로드
        self.background_image = QPixmap(str(FACTORY_IMAGE_PATH))

        self.click_locations = []  # [(x, y), ...] 클릭한 위치 목록
        
        # JSON 파일에서 직사각형 영역 로드
        self.rectangles = self.load_rectangles_from_json()
        
        # 배경 이미지의 실제 렌더링 위치 추적 (paintEvent에서 업데이트)
        self.img_render_x = 0
        self.img_render_y = 0
        self.img_render_width = 0
        self.img_render_height = 0

        self.setMouseTracking(True)
    
    def load_rectangles_from_json(self):
        """rectangle_areas.json 파일에서 영역 정보 로드"""
        json_path = PROJECT_ROOT / "Mobile_LLM" / "ui" / "rectangle_areas.json"
        rectangles = []
        
        try:
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    img_width = data['image_size']['width']
                    img_height = data['image_size']['height']
                    
                    for rect_data in data['rectangles']:
                        rect = RectangleArea(
                            name=rect_data['name'],
                            x1=rect_data['pixel_coords']['x1'],
                            y1=rect_data['pixel_coords']['y1'],
                            x2=rect_data['pixel_coords']['x2'],
                            y2=rect_data['pixel_coords']['y2'],
                            img_width=img_width,
                            img_height=img_height
                        )
                        rectangles.append(rect)
                print(f"✓ {len(rectangles)}개의 영역이 로드되었습니다.")
            else:
                print(f"⚠ rectangle_areas.json 파일을 찾을 수 없습니다: {json_path}")
        except Exception as e:
            print(f"⚠ 영역 로드 중 오류: {e}")
        
        return rectangles

    def world_to_screen(self, world_x, world_y):
        """세계 좌표를 화면 좌표로 변환
        (0,0)은 맵의 밑변 중앙
        """
        # 캔버스 크기
        canvas_width = self.width()
        canvas_height = self.height()

        # 맵의 크기를 캔버스에 맞추기
        px_per_unit_x = canvas_width / self.MAP_WIDTH
        px_per_unit_y = canvas_height / self.MAP_HEIGHT

        # (0, 0)이 밑변 중앙이므로
        # 화면 좌표: 중앙 하단에서 시작
        screen_x = (canvas_width / 2) + world_x * px_per_unit_x
        screen_y = canvas_height - world_y * px_per_unit_y

        return int(screen_x), int(screen_y)

    def screen_to_world(self, screen_x, screen_y):
        """화면 좌표를 세계 좌표로 변환"""
        canvas_width = self.width()
        canvas_height = self.height()

        px_per_unit_x = canvas_width / self.MAP_WIDTH
        px_per_unit_y = canvas_height / self.MAP_HEIGHT

        world_x = (screen_x - canvas_width / 2) / px_per_unit_x
        world_y = (canvas_height - screen_y) / px_per_unit_y

        return round(world_x, 2), round(world_y, 2)

    def screen_to_image_pixel(self, screen_x, screen_y):
        """화면 좌표를 원본 이미지 픽셀 좌표로 변환"""
        if self.img_render_width == 0 or self.img_render_height == 0:
            return None, None
        
        # 이미지 렌더링 영역 내부인지 확인
        if (screen_x < self.img_render_x or screen_x > self.img_render_x + self.img_render_width or
            screen_y < self.img_render_y or screen_y > self.img_render_y + self.img_render_height):
            return None, None
        
        # 렌더링 영역 내 상대 좌표
        rel_x = screen_x - self.img_render_x
        rel_y = screen_y - self.img_render_y
        
        # 원본 이미지 픽셀 좌표로 변환
        if not self.background_image.isNull():
            img_pixel_x = rel_x * self.background_image.width() / self.img_render_width
            img_pixel_y = rel_y * self.background_image.height() / self.img_render_height
            return img_pixel_x, img_pixel_y
        
        return None, None
    
    def mousePressEvent(self, event):
        """마우스 클릭 시 직사각형 영역 선택 토글"""
        if event.button() == Qt.LeftButton:
            # 화면 좌표를 이미지 픽셀 좌표로 변환
            img_pixel_x, img_pixel_y = self.screen_to_image_pixel(event.x(), event.y())
            
            # 클릭한 위치가 어떤 직사각형 안에 있는지 확인
            clicked_rect = None
            if img_pixel_x is not None and img_pixel_y is not None:
                for rect in self.rectangles:
                    if rect.contains_image_point(img_pixel_x, img_pixel_y):
                        clicked_rect = rect
                        break
            
            if clicked_rect:
                # 직사각형을 클릭한 경우 선택 상태 토글
                clicked_rect.toggle_selection()
                print(f"영역 '{clicked_rect.name}' {'선택됨' if clicked_rect.selected else '해제됨'} - 픽셀: ({img_pixel_x:.0f}, {img_pixel_y:.0f})")
            else:
                # 빈 공간을 클릭한 경우 (기존처럼 위치 추가)
                world_pos = self.screen_to_world(event.x(), event.y())
                self.click_locations.append(world_pos)
            
            self.update()

    def paintEvent(self, event):
        """맵 그리기"""
        painter = QPainter(self)

        # 배경 이미지 그리기 및 렌더링 위치 추적
        if not self.background_image.isNull():
            # 캔버스에 맞춰 이미지 스케일 (비율 유지)
            canvas_ratio = self.width() / self.height()
            img_ratio = self.background_image.width() / self.background_image.height()
            
            if canvas_ratio > img_ratio:
                # 높이 기준으로 맞춤
                scaled_image = self.background_image.scaledToHeight(
                    self.height(),
                    Qt.SmoothTransformation
                )
            else:
                # 너비 기준으로 맞춤
                scaled_image = self.background_image.scaledToWidth(
                    self.width(),
                    Qt.SmoothTransformation
                )
            
            # 중앙 정렬
            self.img_render_x = (self.width() - scaled_image.width()) // 2
            self.img_render_y = (self.height() - scaled_image.height()) // 2
            self.img_render_width = scaled_image.width()
            self.img_render_height = scaled_image.height()
            
            painter.drawPixmap(self.img_render_x, self.img_render_y, scaled_image)

        # 그리드 그리기
        self.draw_grid(painter)
        
        # 직사각형 영역들 그리기
        self.draw_rectangles(painter)

        # 로봇 그리기 (0, 0)
        self.draw_robot(painter)

        # 클릭된 위치들을 빨간색 원으로 표시
        for i, location in enumerate(self.click_locations):
            self.draw_circle(painter, location, self.CLICK_COLOR, i)

    def draw_grid(self, painter):
        """배경 그리드 그리기"""
        painter.setPen(QPen(self.GRID_COLOR, self.GRID_WIDTH))

        # 수직선
        for i in range(int(self.MAP_WIDTH) + 1):
            x_world = i - self.MAP_WIDTH / 2
            x_screen, _ = self.world_to_screen(x_world, 0)
            y_top, _ = self.world_to_screen(0, self.MAP_HEIGHT)
            y_bottom, _ = self.world_to_screen(0, 0)
            painter.drawLine(x_screen, y_top, x_screen, y_bottom)

        # 수평선
        for i in range(int(self.MAP_HEIGHT) + 1):
            _, y_screen = self.world_to_screen(0, i)
            x_left, _ = self.world_to_screen(-self.MAP_WIDTH / 2, i)
            x_right, _ = self.world_to_screen(self.MAP_WIDTH / 2, i)
            painter.drawLine(x_left, y_screen, x_right, y_screen)

    def draw_rectangles(self, painter):
        """직사각형 영역들 그리기 (선택된 것만 색상 오버레이)"""
        if self.background_image.isNull() or self.img_render_width == 0:
            return
        
        for rect in self.rectangles:
            if rect.selected:
                # 이미지 렌더링 위치를 고려한 화면 좌표로 변환
                x1, y1, x2, y2 = rect.get_screen_coords(
                    self.img_render_x, 
                    self.img_render_y,
                    self.img_render_width, 
                    self.img_render_height,
                    self.background_image.width(),
                    self.background_image.height()
                )
                
                # 선택된 영역에만 색상 오버레이
                fill_color = QColor(self.RECT_SELECTED_COLOR)
                fill_color.setAlpha(120)  # 반투명
                
                # 직사각형 그리기
                painter.setBrush(QBrush(fill_color))
                painter.setPen(QPen(self.RECT_BORDER_COLOR, 3))
                painter.drawRect(x1, y1, x2 - x1, y2 - y1)
                
                # 영역 이름 표시
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.setFont(QFont("Arial", 12, QFont.Bold))
                text_x = (x1 + x2) // 2 - 25
                text_y = (y1 + y2) // 2
                painter.drawText(text_x, text_y, rect.name)

    def draw_robot(self, painter):
        """로봇(START POINT) 표시는 하지 않음"""
        return

    def draw_circle(self, painter, location, color, index):
        """클릭한 위치에 원 표시"""
        screen_pos = self.world_to_screen(location[0], location[1])
        
        # 빨간색 원 그리기 (투명도 조절)
        transparent_color = QColor(color)
        transparent_color.setAlpha(100)  # 투명도 설정 (0-255, 낮을수록 투명)
        
        painter.setBrush(QBrush(transparent_color))
        painter.setPen(QPen(color, 2))
        painter.drawEllipse(screen_pos[0] - self.CLICK_RADIUS, 
                           screen_pos[1] - self.CLICK_RADIUS,
                           self.CLICK_RADIUS * 2,
                           self.CLICK_RADIUS * 2)

    def get_click_locations(self):
        """클릭한 위치 데이터 반환 (기존 점 + 선택된 직사각형)"""
        result = []
        
        # 선택된 직사각형 영역들 추가
        for rect in self.rectangles:
            if rect.selected:
                # 직사각형 중심점을 월드 좌표로 변환
                center_pixel_x = (rect.x1 + rect.x2) / 2
                center_pixel_y = (rect.y1 + rect.y2) / 2
                
                # 이미지 비율 좌표로 변환
                ratio_x = center_pixel_x / rect.img_width
                ratio_y = center_pixel_y / rect.img_height
                
                # 캔버스 좌표로 변환 후 월드 좌표로 변환
                canvas_x = ratio_x * self.width()
                canvas_y = ratio_y * self.height()
                world_x, world_y = self.screen_to_world(canvas_x, canvas_y)
                
                result.append({
                    "id": len(result),
                    "name": rect.name,
                    "x": world_x,
                    "y": world_y,
                    "type": "rectangle",
                    "pixel_bounds": {
                        "x1": rect.x1,
                        "y1": rect.y1,
                        "x2": rect.x2,
                        "y2": rect.y2
                    }
                })
        
        # 기존 클릭 위치들 추가
        for i, location in enumerate(self.click_locations):
            result.append({
                "id": len(result),
                "x": location[0],
                "y": location[1],
                "type": "point"
            })
        
        return result

    def clear_locations(self):
        """모든 클릭 위치 및 선택 삭제"""
        self.click_locations = []
        for rect in self.rectangles:
            rect.selected = False
        self.update()


class CommandUI(QMainWindow):
    """메인 UI 윈도우"""

    # 타이틀 글자 크기 설정 (조절 가능)
    TITLE_FONT_SIZE = 72

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle("Navigation Command Interface")
        self.setGeometry(100, 100, 1000, 600)

        # 중앙 위젯
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 최상위 레이아웃 (수직)
        main_vertical_layout = QVBoxLayout()
        central_widget.setLayout(main_vertical_layout)

        # 타이틀 라벨 (상단 중앙)
        title_label = QLabel("HMS lab")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont("Arial", self.TITLE_FONT_SIZE, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: rgb(105, 1, 8);")
        main_vertical_layout.addWidget(title_label)

        # 메인 콘텐츠 레이아웃 (수평)
        main_layout = QHBoxLayout()
        main_vertical_layout.addLayout(main_layout)

        # 좌측: 맵 캔버스
        self.map_canvas = MapCanvas()
        main_layout.addWidget(self.map_canvas, 3)

        # 우측: 컨트롤 패널
        right_panel = QVBoxLayout()

        # 설명 라벨 (글자 크기 2배)
        description = QLabel("이미지의 직사각형 영역을 클릭하세요\n선택된 영역은 빨간색으로 표시됩니다")
        description.setFont(QFont("Arial", 20))
        right_panel.addWidget(description)

        # 채팅 디스플레이 영역
        chat_label = QLabel("대화 기록:")
        chat_label.setFont(QFont("Arial", 20))
        right_panel.addWidget(chat_label)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Arial", 16))
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #f5f5f5;
                border: 2px solid #ccc;
                border-radius: 5px;
                padding: 10px;
            }
        """)
        self.chat_display.setMinimumHeight(400)
        right_panel.addWidget(self.chat_display)

        # 텍스트 입력 창 (글자 크기 2배)
        input_label = QLabel("명령어 입력:")
        input_label.setFont(QFont("Arial", 20))
        right_panel.addWidget(input_label)

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("명령을 입력하세요")
        self.command_input.setMinimumHeight(80)
        self.command_input.setFont(QFont("Arial", 18))
        self.command_input.returnPressed.connect(self.on_submit)
        right_panel.addWidget(self.command_input)

        # 입력 버튼 (글자 크기 2배)
        self.submit_button = QPushButton("입력")
        self.submit_button.setMinimumHeight(80)
        self.submit_button.setFont(QFont("Arial", 20))
        self.submit_button.clicked.connect(self.on_submit)
        right_panel.addWidget(self.submit_button)

        # 초기화 버튼 (글자 크기 2배)
        clear_button = QPushButton("위치 초기화")
        clear_button.setMinimumHeight(80)
        clear_button.setFont(QFont("Arial", 20))
        clear_button.clicked.connect(self.map_canvas.clear_locations)
        right_panel.addWidget(clear_button)

        # 종료 버튼 (글자 크기 2배)
        exit_button = QPushButton("종료")
        exit_button.setMinimumHeight(80)
        exit_button.setFont(QFont("Arial", 20))
        exit_button.clicked.connect(self.close)
        right_panel.addWidget(exit_button)

        # 상태 라벨 (글자 크기 2배)
        right_panel.addWidget(QLabel(""))
        self.status_label = QLabel("대기 중...")
        self.status_label.setFont(QFont("Arial", 18))
        right_panel.addWidget(self.status_label)

        right_panel.addStretch()

        # 우측 패널을 메인 레이아웃에 추가
        main_layout.addLayout(right_panel, 1)

        # 마지막 제출 시 위치 데이터 저장 (위치 변경시에만 전송하기 위함)
        self.last_submitted_locations = []

    def add_chat_message(self, sender, message, color="black"):
        """채팅창에 메시지 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f'<p style="margin: 5px 0; color: {color};"><b>[{timestamp}] {sender}:</b><br>{message}</p>'
        self.chat_display.append(formatted_message)
        # 스크롤을 맨 아래로
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_submit(self):
        """입력 버튼 클릭 시 처리"""
        command_text = self.command_input.text().strip()

        if not command_text:
            return

        # 사용자 입력을 채팅창에 표시
        self.add_chat_message("사용자", command_text, "#0066cc")

        # 입력창 초기화
        self.command_input.clear()

        all_locations_data = self.map_canvas.get_click_locations()

        # 위치 상태 변경 여부 확인 (이전 저장된 위치와 현재 위치 비교)
        locations_changed = json.dumps(all_locations_data, sort_keys=True) != json.dumps(self.last_submitted_locations, sort_keys=True)

        # 위치가 변경되었으면 현재 위치 데이터 전송, 아니면 빈 배열 전송
        if locations_changed:
            locations_to_send = all_locations_data
        else:
            locations_to_send = []

        # 위치 좌표 문자열 생성 (A, B, C, ... 순서로, 무제한)
        location_coords = []
        for i, location in enumerate(locations_to_send):
            # 라벨 생성: A-Z (0-25), AA-AZ (26-51), BA-BZ (52-77), ...
            if i < 26:
                label = chr(ord('A') + i)
            else:
                first_idx = (i - 26) // 26
                second_idx = (i - 26) % 26
                label = chr(ord('A') + first_idx) + chr(ord('A') + second_idx)
            
            x = location["x"]
            y = location["y"]
            location_coords.append(f"{label}({x},{y})")

        # 출력 형식: command A(x1,y1), B(x2,y2)
        if location_coords:
            output_string = f"{command_text} {', '.join(location_coords)}"
        else:
            output_string = command_text

        print(f"\n{output_string}")

        # JSON 데이터 구성
        output_data = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "map_size": {
                    "width": self.map_canvas.MAP_WIDTH,
                    "height": self.map_canvas.MAP_HEIGHT
                }
            },
            "robot": {
                "position": {"x": self.map_canvas.ROBOT_X, "y": self.map_canvas.ROBOT_Y},
                "size": {
                    "width": self.map_canvas.ROBOT_SIZE,
                    "height": self.map_canvas.ROBOT_SIZE
                }
            },
            "locations": locations_to_send,
            "command": command_text,
            "formatted_output": output_string
        }

        # 서버로 전송 시도
        server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000")
        try:
            # meta에 위치 데이터 담아서 전송 (변경되었을 때만 실제 데이터 포함)
            payload = {
                "command": command_text,
                "meta": {
                    "locations": locations_to_send,
                    "map_metadata": output_data["metadata"],
                    "robot": output_data["robot"],
                    "formatted_output": output_string
                }
            }

            response = requests.post(
                f"{server_url}/run_command",
                json=payload,
                timeout=30
            )

            # 서버 응답 출력
            try:
                server_response = response.json()
                print(f"\n[서버 응답] {response.status_code}")
                print(json.dumps(server_response, indent=2, ensure_ascii=False))

                # 서버 응답을 채팅창에 표시
                response_text = json.dumps(server_response, indent=2, ensure_ascii=False)
                self.add_chat_message("서버", response_text, "#009900")

                status_msg = f"✓ 서버 전송 완료 ({response.status_code})\n위치 {len(locations_to_send)}개"
            except:
                print(f"\n[서버 응답] {response.status_code}: {response.text}")

                # 서버 응답 (JSON 파싱 실패)
                self.add_chat_message("서버", f"[{response.status_code}] {response.text}", "#009900")

                status_msg = f"✓ 서버 전송 완료 ({response.status_code})"

            self.status_label.setText(status_msg)

        except requests.exceptions.RequestException as e:
            # 서버 연결 실패 - 파일로 저장
            print(f"\n[경고] 서버 연결 실패 ({e}). 파일로 저장합니다.")

            # 채팅창에 에러 표시
            self.add_chat_message("시스템", f"⚠️ 서버 연결 실패: {str(e)}", "#cc0000")

            OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = OUTPUT_DIR / f"command_{timestamp}.json"

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)

            # 채팅창에 파일 저장 알림
            self.add_chat_message("시스템", f"💾 명령이 파일로 저장되었습니다: {output_file.name}", "#ff6600")

            self.status_label.setText(
                f"✗ 서버 오류 → 파일 저장됨\n{output_file.name}"
            )
            print(f"[저장됨] {output_file}")

        # 현재 위치 상태를 저장 (다음 비교용)
        self.last_submitted_locations = all_locations_data



def main():
    app = QApplication(sys.argv)
    window = CommandUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
