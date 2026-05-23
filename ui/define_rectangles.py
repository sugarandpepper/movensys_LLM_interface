import cv2
import json
from pathlib import Path

# 이미지 경로
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

# 원본 이미지 복사본
img_original = img.copy()
img_display = img.copy()

# 변수
rectangles = []  # 저장된 직사각형 리스트 [(x1, y1, x2, y2, name), ...]
drawing = False  # 그리기 상태
start_point = None
current_point = None

def mouse_callback(event, x, y, flags, param):
    global drawing, start_point, current_point, img_display
    
    if event == cv2.EVENT_LBUTTONDOWN:
        # 드래그 시작
        drawing = True
        start_point = (x, y)
        current_point = (x, y)
    
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            # 드래그 중
            current_point = (x, y)
            img_display = img.copy()
            
            # 기존 저장된 직사각형들 표시
            for i, rect in enumerate(rectangles):
                cv2.rectangle(img_display, (rect[0], rect[1]), (rect[2], rect[3]), (0, 255, 0), 2)
                cv2.putText(img_display, rect[4], (rect[0], rect[1]-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            # 현재 그리고 있는 직사각형 표시 (빨간색)
            cv2.rectangle(img_display, start_point, current_point, (0, 0, 255), 2)
            cv2.imshow("Rectangle Definer", img_display)
    
    elif event == cv2.EVENT_LBUTTONUP:
        # 드래그 끝
        drawing = False
        current_point = (x, y)
        
        # 직사각형 크기 확인 (최소 크기 체크)
        if abs(current_point[0] - start_point[0]) > 10 and abs(current_point[1] - start_point[1]) > 10:
            # 직사각형 추가
            x1 = min(start_point[0], current_point[0])
            y1 = min(start_point[1], current_point[1])
            x2 = max(start_point[0], current_point[0])
            y2 = max(start_point[1], current_point[1])
            
            name = f"Zone_{len(rectangles) + 1}"
            rectangles.append((x1, y1, x2, y2, name))
            
            print(f"{name} 추가됨: ({x1}, {y1}) ~ ({x2}, {y2})")
            
            # 화면 업데이트
            img.fill(0)
            img[:] = img_original[:]
            for i, rect in enumerate(rectangles):
                cv2.rectangle(img, (rect[0], rect[1]), (rect[2], rect[3]), (0, 255, 0), 2)
                cv2.putText(img, rect[4], (rect[0], rect[1]-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            img_display = img.copy()
            cv2.imshow("Rectangle Definer", img_display)

# 메인
window_name = "Rectangle Definer"
cv2.imshow(window_name, img_display)
cv2.setMouseCallback(window_name, mouse_callback)

print("=" * 60)
print("직사각형 영역 정의 도구")
print("=" * 60)
print("사용법:")
print("  - 마우스 드래그로 직사각형 영역을 그리세요")
print("  - 'u' : 마지막 직사각형 삭제")
print("  - 's' : 정의한 영역을 JSON 파일로 저장")
print("  - 'r' : 모두 초기화")
print("  - 'ESC' : 종료")
print("=" * 60)

while True:
    key = cv2.waitKey(1) & 0xFF
    
    if key == 27:  # ESC
        print("종료합니다.")
        break
    
    elif key == ord('u'):  # Undo
        if rectangles:
            removed = rectangles.pop()
            print(f"{removed[4]} 삭제됨")
            
            # 화면 업데이트
            img[:] = img_original[:]
            for i, rect in enumerate(rectangles):
                cv2.rectangle(img, (rect[0], rect[1]), (rect[2], rect[3]), (0, 255, 0), 2)
                cv2.putText(img, rect[4], (rect[0], rect[1]-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            
            img_display = img.copy()
            cv2.imshow(window_name, img_display)
    
    elif key == ord('r'):  # Reset
        rectangles.clear()
        img[:] = img_original[:]
        img_display = img.copy()
        cv2.imshow(window_name, img_display)
        print("모든 영역이 초기화되었습니다.")
    
    elif key == ord('s'):  # Save
        if not rectangles:
            print("저장할 영역이 없습니다!")
            continue
        
        # JSON 형식으로 저장
        output_data = {
            "image_size": {
                "width": img.shape[1],
                "height": img.shape[0]
            },
            "rectangles": []
        }
        
        for i, rect in enumerate(rectangles):
            output_data["rectangles"].append({
                "name": rect[4],
                "pixel_coords": {
                    "x1": rect[0],
                    "y1": rect[1],
                    "x2": rect[2],
                    "y2": rect[3]
                },
                "center": {
                    "x": (rect[0] + rect[2]) // 2,
                    "y": (rect[1] + rect[3]) // 2
                },
                "size": {
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1]
                }
            })
        
        # 파일 저장
        output_file = Path(__file__).parent / "rectangle_areas.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'=' * 60}")
        print(f"✓ 영역 정보가 저장되었습니다: {output_file}")
        print(f"총 {len(rectangles)}개의 영역")
        print(json.dumps(output_data, indent=2, ensure_ascii=False))
        print(f"{'=' * 60}\n")

cv2.destroyAllWindows()
