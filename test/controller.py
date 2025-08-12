import serial, io, time, requests, cv2, os
from serial.serialutil import SerialException
from google.cloud import storage

# ───────── 기본 설정
PORT = '/dev/ttyACM0'
BAUD = 9600

SNAP1_KEYWORD = "SNAP1"
SNAP2_KEYWORD = "SNAP2"

URL_CLASSIFY = "http://34.64.178.127:8100/classify"
URL_DEFECT   = "http://34.64.178.127:8000/defect"

CAM_IR1, CAM_IR2 = 0, 2   # /dev/video0, /dev/video2 (환경에 맞게!)

# ───────── 시리얼
def open_serial():
    while True:
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            time.sleep(2)
            ser.reset_input_buffer()
            print("[*] Serial Connected")
            return ser
        except SerialException as e:
            print("[!] Serial open failed:", e)
            time.sleep(3)

# ───────── 카메라 캡처
def capture_usbcam(index, size=(1280,720), warmup=0.7):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Cam {index} open fail")
    w,h = size; cap.set(cv2.CAP_PROP_FRAME_WIDTH,w); cap.set(cv2.CAP_PROP_FRAME_HEIGHT,h)
    time.sleep(warmup)
    ok, frame = cap.read(); cap.release()
    if not ok: raise RuntimeError("Frame read fail")
    return frame

# ───────── 서버 요청
def post_image(url, image_bytes, timeout=5):
    stream = io.BytesIO(image_bytes); stream.seek(0)
    files  = {'file': ('img.jpg', stream, 'image/jpeg')}
    return requests.post(url, files=files, params={'return_type':'json'}, timeout=timeout)

# ───────── SNAP1 (IR1)
def handle_snap1(ser):
    try:
        frame = capture_usbcam(CAM_IR1)
        _, buf = cv2.imencode('.jpg', frame)
        r = post_image(URL_DEFECT, buf.tobytes())
        if r.status_code == 200:
            label = r.json().get("label", "O")
            print("SNAP1 label:", label)
            if label == "X":
                ser.write(b"X\n")        # 결함 ‑> X만 전송
            else:
                ser.write(b"GO\n")       # 정상
        else:
            print("SNAP1 server error", r.status_code)
            ser.write(b"GO\n")
    except Exception as e:
        print("SNAP1 error:", e)
        ser.write(b"GO\n")

# ───────── SNAP2 (IR2)
def handle_snap2(ser):
    try:
        frame = capture_usbcam(CAM_IR2)
        _, buf = cv2.imencode('.jpg', frame)
        r = post_image(URL_CLASSIFY, buf.tobytes(), timeout=30)
        if r.status_code == 200:
            grade = r.json().get("label", "O")  # "A" "B" "O"
            ser.write(f"RESULT:{grade}\n".encode())
        else:
            print("SNAP2 server error", r.status_code)
            ser.write(b"GO\n")
    except Exception as e:
        print("SNAP2 error:", e)
        ser.write(b"GO\n")

# ───────── 메인 루프
def main():
    ser = open_serial()
    try:
        while True:
            line = ser.readline().decode(errors='ignore').strip()
            if not line: continue
            print("Arduino:", line)

            if line == SNAP1_KEYWORD: handle_snap1(ser)
            elif line == SNAP2_KEYWORD: handle_snap2(ser)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()

if __name__ == "__main__":
    main()
