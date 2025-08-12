# cam.py — 실캡처 기반 헬스체크 + 카메라 충돌 방지(락)
import io
import cv2
import json
import time
import threading
import requests
import serial
from serial.serialutil import SerialException
from google.cloud import storage

# ─────────────────────────────
# 기본 설정
PORT = '/dev/ttyACM0'
BAUD = 9600

SNAP1_KEYWORD = "SNAP1"   # 결함 검사 트리거
SNAP2_KEYWORD = "SNAP2"   # 등급 검사 트리거

URL_SNAP1 = 'http://34.64.178.127:8000/defect'
URL_SNAP2 = 'http://34.64.178.127:8100/classify'

GCS_KEY_PATH = "service-account.json"

# 이미지 업로드 버킷/폴더
BUCKET_NAME = "zezeone_image"
GCS_FOLDER_SNAP1 = "raw_defect"
GCS_FOLDER_SNAP2 = "raw_grade"

# 헬스 JSON 업로드 버킷/폴더
HEALTH_BUCKET_NAME = "zezeone_health"
HEALTH_FOLDER = "health_check"
GCS_STATUS_OBJECT = f"{HEALTH_FOLDER}/status.json"
HEALTH_INTERVAL = 60  # 초

# 카메라
CAM_IR1 = 2    # 결함용
CAM_IR2 = 0    # 등급용
RESOLUTION = (1280, 720)

# ─────────────────────────────
# GCS 클라이언트(전역 재사용)
_gcs_client = storage.Client.from_service_account_json(GCS_KEY_PATH)
_img_bucket = _gcs_client.bucket(BUCKET_NAME)
_health_bucket = _gcs_client.bucket(HEALTH_BUCKET_NAME)

# 카메라 충돌 방지용 락 (카메라별 독립)
_cam_locks = {
    CAM_IR1: threading.Lock(),
    CAM_IR2: threading.Lock(),
}
CAM_LOCK_TIMEOUT = 3.0  # 초 (캡처 시작 대기 한도)

# ─────────────────────────────
def open_serial():
    while True:
        try:
            ser = serial.Serial(PORT, BAUD, timeout=1)
            time.sleep(2)
            ser.reset_input_buffer()
            print(f"[*] Serial connected: {PORT}")
            return ser
        except SerialException as e:
            print("[!] Serial open failed, retrying in 3s:", e)
            time.sleep(3)

# 락을 잡고 안전하게 한 프레임 캡처
def capture_image_locked(index: int):
    lock = _cam_locks.get(index)
    if lock is None:
        # 정의되지 않은 카메라인 경우도 안전하게 단일 락 사용
        lock = _cam_locks.setdefault(index, threading.Lock())

    acquired = lock.acquire(timeout=CAM_LOCK_TIMEOUT)
    if not acquired:
        raise RuntimeError(f"Camera {index} busy (lock timeout)")

    try:
        cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"Camera {index} open failed")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
        time.sleep(0.7)  # 센서 안정화
        ok, frame = cap.read()
        cap.release()
        return frame if ok else None
    finally:
        lock.release()

def encode_jpeg(frame):
    ok, buf = cv2.imencode('.jpg', frame)
    return buf.tobytes() if ok else None

def upload_to_gcs(image_bytes: bytes, filename: str, folder: str):
    try:
        blob = _img_bucket.blob(f"{folder}/{filename}")
        blob.upload_from_string(image_bytes, content_type='image/jpeg')
        print(f"[GCS] Uploaded: gs://{BUCKET_NAME}/{folder}/{filename}")
        return blob.public_url
    except Exception as e:
        print("[!] GCS upload failed:", e)
        return None

def post_image_to_server(image_bytes: bytes, url: str, retries: int = 3):
    for i in range(retries):
        try:
            stream = io.BytesIO(image_bytes)
            files = {'file': ('image.jpg', stream, 'image/jpeg')}
            resp = requests.post(url, files=files, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            print(f"[!] Server error {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"[!] Server request failed ({i+1}/{retries}):", e)
        time.sleep(0.5)
    return None

# ─────────────────────────────
# SNAP 처리
def handle_snap1(ser):
    try:
        frame = capture_image_locked(CAM_IR1)
        if frame is None:
            raise ValueError("Camera frame is None")
        image_bytes = encode_jpeg(frame)
        if not image_bytes:
            raise ValueError("JPEG encoding failed")

        ts = int(time.time())
        filename = f"snap1_{ts}.jpg"

        if not upload_to_gcs(image_bytes, filename, GCS_FOLDER_SNAP1):
            ser.write(b"GO\n")
            return

        result = post_image_to_server(image_bytes, URL_SNAP1)
        label = (result or {}).get("label")

        if label == "X":
            ser.write(b"X\n")
            print("[SNAP1] Defect → sent: X")
        else:
            ser.write(b"GO\n")
            print("[SNAP1] Normal → sent: GO")
    except Exception as e:
        print("[!] SNAP1 error:", e)
        ser.write(b"GO\n")

def handle_snap2(ser):
    try:
        frame = capture_image_locked(CAM_IR2)
        if frame is None:
            raise ValueError("Camera frame is None")
        image_bytes = encode_jpeg(frame)
        if not image_bytes:
            raise ValueError("JPEG encoding failed")

        ts = int(time.time())
        filename = f"snap2_{ts}.jpg"

        upload_to_gcs(image_bytes, filename, GCS_FOLDER_SNAP2)

        result = post_image_to_server(image_bytes, URL_SNAP2)
        grade = (result or {}).get("label")

        if grade:
            ser.write(f"RESULT:{grade}\n".encode())
            print(f"[SNAP2] Grade → sent: RESULT:{grade}")
        else:
            ser.write(b"GO\n")
            print("[SNAP2] Grade missing → sent: GO")
    except Exception as e:
        print("[!] SNAP2 error:", e)
        ser.write(b"GO\n")

# ─────────────────────────────
# 헬스체크(실캡처 기반 + GCS 업로드)
def check_camera(index: int) -> str:
    try:
        frame = capture_image_locked(index)
        return "ok" if frame is not None else "fail"
    except Exception:
        return "fail"

def check_server_health(url: str) -> str:
    try:
        r = requests.head(url, timeout=2)
        if r.status_code == 200:
            return "ok"
        if r.status_code in (400, 404, 405, 500):
            g = requests.get(url, timeout=3)
            return "ok" if g.status_code == 200 else "fail"
        return "fail"
    except Exception:
        try:
            g = requests.get(url, timeout=3)
            return "ok" if g.status_code == 200 else "fail"
        except Exception:
            return "fail"

def report_health_to_gcs():
    now = int(time.time())
    status = {
        "ts": now,
        "ir1": check_camera(CAM_IR1),  # 실캡처 기반
        "ir2": check_camera(CAM_IR2),  # 실캡처 기반
        "defect": check_server_health("http://34.64.178.127:8000/health"),
        "classify": check_server_health("http://34.64.178.127:8100/health"),
    }
    ok_all = (
        status.get("ir1") == "ok" and
        status.get("ir2") == "ok" and
        status.get("defect") == "ok" and
        status.get("classify") == "ok"
    )
    status["overall"] = "ok" if ok_all else "fail"

    try:
        blob = _health_bucket.blob(GCS_STATUS_OBJECT)
        blob.cache_control = "no-store, max-age=0"
        blob.upload_from_string(json.dumps(status), content_type="application/json")
        print(f"[Health] GCS uploaded gs://{HEALTH_BUCKET_NAME}/{GCS_STATUS_OBJECT} | {status}")
    except Exception as e:
        print("[!] Health GCS upload failed:", e)

def start_healthcheck_loop():
    def loop():
        while True:
            report_health_to_gcs()
            time.sleep(HEALTH_INTERVAL)
    threading.Thread(target=loop, daemon=True).start()

# ─────────────────────────────
def main():
    ser = open_serial()
    report_health_to_gcs()
    start_healthcheck_loop()

    try:
        while True:
            line = ser.readline().decode(errors='ignore').strip()
            if not line:
                continue
            print("[ARDUINO]", line)

            if line == SNAP1_KEYWORD:
                handle_snap1(ser)
            elif line == SNAP2_KEYWORD:
                handle_snap2(ser)

    except KeyboardInterrupt:
        print("\n[*] Stopped by user")
    except SerialException as e:
        print("[!] Serial error:", e)
    finally:
        try:
            ser.close()
        except Exception:
            pass

# ─────────────────────────────
if __name__ == "__main__":
    main()
