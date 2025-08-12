import os
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
PORT = '/dev/ttyACM0'               # Arduino와 연결된 시리얼 포트
BAUD = 9600                         # 시리얼 통신 속도

SNAP1_KEYWORD = "SNAP1"             # 결함 검사 트리거 신호
SNAP2_KEYWORD = "SNAP2"             # 등급 검사 트리거 신호

URL_SNAP1 = 'http://34.64.178.127:8000/defect'     # 결함 판단 AI 서버
URL_SNAP2 = 'http://34.64.178.127:8100/classify'   # 등급 판단 Rule 서버

GCS_KEY_PATH = "service-account.json"              # GCP 인증 키 (권한 600 권장)

# 이미지 업로드용 버킷/폴더
BUCKET_NAME = "zezeone_image"
GCS_FOLDER_SNAP1 = "raw_defect"
GCS_FOLDER_SNAP2 = "raw_grade"

# 헬스 JSON 업로드용 버킷/폴더
HEALTH_BUCKET_NAME = "zezeone_health"
HEALTH_FOLDER = "health_check"
GCS_STATUS_OBJECT = f"{HEALTH_FOLDER}/status.json"  # 장비ID 별로 경로 분리 권장
HEALTH_INTERVAL =  60 

# 카메라
CAM_IR1 = 2                         # 일반 카메라 인덱스 (결함 검사용)
CAM_IR2 = 0                         # 현미경 카메라 인덱스 (등급 검사용)
RESOLUTION = (1280, 720)            # 카메라 캡처 해상도

# ─────────────────────────────
# GCS 클라이언트(전역 재사용)
_gcs_client = storage.Client.from_service_account_json(GCS_KEY_PATH)
_img_bucket = _gcs_client.bucket(BUCKET_NAME)
_health_bucket = _gcs_client.bucket(HEALTH_BUCKET_NAME)

# ─────────────────────────────
# 시리얼 포트 열기
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

# 카메라로 이미지 캡처 (단발)
def capture_image(index: int):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Camera {index} open failed")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    time.sleep(0.7)
    ok, frame = cap.read()
    cap.release()
    return frame if ok else None

# 이미지 JPEG 인코딩
def encode_jpeg(frame):
    ok, buf = cv2.imencode('.jpg', frame)
    return buf.tobytes() if ok else None

# GCS 업로드(이미지)
def upload_to_gcs(image_bytes: bytes, filename: str, folder: str):
    try:
        blob = _img_bucket.blob(f"{folder}/{filename}")
        blob.upload_from_string(image_bytes, content_type='image/jpeg')
        print(f"[GCS] Uploaded: gs://{BUCKET_NAME}/{folder}/{filename}")
        return blob.public_url
    except Exception as e:
        print("[!] GCS upload failed:", e)
        return None

# 이미지 AI 서버로 전송 후 응답 반환
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

# SNAP1 처리 (결함 검사)
def handle_snap1(ser):
    try:
        frame = capture_image(CAM_IR1)
        if frame is None:
            raise ValueError("Camera frame is None")
        image_bytes = encode_jpeg(frame)
        if not image_bytes:
            raise ValueError("JPEG encoding failed")

        ts = int(time.time())
        filename = f"snap1_{ts}.jpg"

        # 업로드 실패해도 라인은 멈추지 않게 GO
        if not upload_to_gcs(image_bytes, filename, GCS_FOLDER_SNAP1):
            ser.write(b"GO\n")
            return

        result = post_image_to_server(image_bytes, URL_SNAP1)
        label = result.get("label") if result else None

        if label == "X":
            ser.write(b"X\n")
            print("[SNAP1] Defect → sent: X")
        else:
            ser.write(b"GO\n")
            print("[SNAP1] Normal → sent: GO")
    except Exception as e:
        print("[!] SNAP1 error:", e)
        ser.write(b"GO\n")

# SNAP2 처리 (등급 판별)
def handle_snap2(ser):
    try:
        frame = capture_image(CAM_IR2)
        if frame is None:
            raise ValueError("Camera frame is None")
        image_bytes = encode_jpeg(frame)
        if not image_bytes:
            raise ValueError("JPEG encoding failed")

        ts = int(time.time())
        filename = f"snap2_{ts}.jpg"

        upload_to_gcs(image_bytes, filename, GCS_FOLDER_SNAP2)

        result = post_image_to_server(image_bytes, URL_SNAP2)
        grade = result.get("label") if result else None

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
# 헬스체크(초저부하): /dev/video* 존재 + 서버 헬스 HEAD(미지원 시 GET)
def usb_present(dev_index: int) -> str:
    path = f"/dev/video{dev_index}"
    return "ok" if os.path.exists(path) else "fail"

def check_server_health(url: str) -> str:
    try:
        r = requests.head(url, timeout=2)
        if r.status_code == 200:
            return "ok"
        # 일부 서버는 HEAD 미지원(405 등) → GET로 재시도
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
        "ir1": usb_present(CAM_IR1),
        "ir2": usb_present(CAM_IR2),
        "defect": check_server_health("http://34.64.178.127:8000/health"),
        "classify": check_server_health("http://34.64.178.127:8100/health"),
    }
    ok_all = (
        status["ir1"] == "ok" and 
        status["ir2"] == "ok" and
        status["defect"] == "ok" and
        status["classify"] == "ok"
    )
    status["overall"] = "ok" if ok_all else "fail"

    try:
        blob = _health_bucket.blob(GCS_STATUS_OBJECT)
        blob.cache_control = "no-store, max-age=0"       # 캐시 방지
        blob.content_type = "application/json"
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
# 메인 실행 루프
def main():
    ser = open_serial()

    # 첫 헬스 업로드 + 주기 실행
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
