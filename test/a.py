import cv2

CAM_IR2 = 0 # Snap2 카메라 인덱스 (보통 0번, 환경에 따라 확인)
WIN_NAME = "Snap2 Live"

def live_snap2_camera(cam_index=CAM_IR2, size=(1280, 720)):
    cap = cv2.VideoCapture(cam_index, cv2.CAP_V4L2)
    if not cap.isOpened():
        print(f"[!] 카메라 {cam_index} 오픈 실패")
        return

    if size:
        w, h = size
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    print(f"[*] Snap1 실시간 미리보기 시작 (종료: q 또는 ESC)")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[!] 프레임 수신 실패")
            break
        cv2.imshow(WIN_NAME, frame)

        key = cv2.waitKey(1)
        if key == ord('q') or key == 27:  # q or ESC
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[*] Snap2 라이브뷰 종료")

if __name__ == "__main__":
    live_snap2_camera()
