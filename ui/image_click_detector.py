import cv2
import os
from pathlib import Path

# 현재 폴더의 image 폴더 경로
image_folder = Path(__file__).parent / "image"
image_path = image_folder / "factory.png"

# 이미지 로드
if not image_path.exists():
    print(f"이미지를 찾을 수 없습니다: {image_path}")
    exit(1)

img = cv2.imread(str(image_path))
if img is None:
    print(f"이미지를 읽을 수 없습니다: {image_path}")
    exit(1)

# 클릭 이벤트 처리 함수
def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:  # 마우스 왼쪽 버튼 클릭
        print(f"클릭 위치: X={x}, Y={y}")
        # 클릭한 위치에 원 표시
        cv2.circle(img, (x, y), 5, (0, 255, 0), -1)
        # 좌표 텍스트 표시
        cv2.putText(img, f"({x}, {y})", (x + 10, y - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.imshow("Image Click Detector", img)

# 이미지 표시
window_name = "Image Click Detector"
cv2.imshow(window_name, img)
print(f"이미지가 열렸습니다: {image_path}")
print("이미지를 클릭하여 좌표를 확인하세요. (ESC를 눌러 종료)")

# 마우스 콜백 등록
cv2.setMouseCallback(window_name, mouse_callback)

# ESC 키를 눌 때까지 대기
while True:
    key = cv2.waitKey(1) & 0xFF
    if key == 27:  # ESC 키
        print("종료합니다.")
        break

cv2.destroyAllWindows()
