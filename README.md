# 🎥 cam.py - 자동 품질 검사 컨트롤러 (v2)

Python | OpenCV | Serial | Google Cloud Storage | Requests

---

## 🎯 프로젝트 개요

`cam.py`는 아두이노와 라즈베리파이, AI 서버와의 통신을 통해 자동 품질 검사 프로세스를 제어하는 메인 컨트롤러입니다.
두 대의 카메라(결함 검사용, 등급 판정용)를 사용하여 **결함 검사(SNAP1)**와 **등급 판정(SNAP2)**을 수행하며, 촬영된 이미지는 Google Cloud Storage(GCS)에 실시간으로 백업됩니다.

특히, 여러 프로세스(메인 로직, 헬스체크)가 동시에 카메라에 접근할 때 발생하는 충돌을 방지하기 위한 **카메라 락(Lock) 기능**이 구현되어 있습니다. 또한, 시스템의 주요 구성 요소(카메라, 서버) 상태를 주기적으로 점검하여 **GCS에 상태 리포트를 업로드**함으로써 운영 안정성을 크게 향상시켰습니다.

---

## ✨ 주요 기능

- **SNAP1: 결함 검사**
  - 결함 검사용 카메라(CAM_IR1)로 촬영된 이미지를 AI 서버로 전송합니다.
  - 서버 응답이 `{"label": "X"}`이면 불량(X)으로 처리하고, 정상이면 GO 신호를 아두이노로 전송합니다.

- **SNAP2: 등급 판정**
  - 등급 판정용 카메라(CAM_IR2)로 촬영된 이미지를 Rule 기반 서버로 전송합니다.
  - 서버 응답 `{"label": "A"}`에 따라 `RESULT:A` 형식으로 아두이노에 등급을 전송합니다.

- **GCS 업로드**
  - **이미지 백업**: SNAP1 이미지는 `raw_defect/` 폴더에, SNAP2 이미지는 `raw_grade/` 폴더에 업로드됩니다.
  - **헬스체크 리포트**: 시스템 상태 점검 결과는 별도의 버킷에 `health_check/status.json`으로 주기적으로 업로드됩니다.

- **안정성 기능**
  - **카메라 락**: `threading.Lock`을 사용하여 여러 스레드에서 카메라 자원을 안전하게 사용합니다.
  - **주기적 헬스체크**: 백그라운드 스레드에서 카메라와 서버 상태를 주기적으로 점검합니다.

---

## 🧭 시스템 워크플로우

### 1️⃣ SNAP1 - 결함 검사

1. 아두이노로부터 `"SNAP1"` 신호 수신
2. 결함 검사용 카메라(CAM_IR1)로 이미지 촬영 (락 확보)
3. GCS `raw_defect/` 폴더에 이미지 업로드
4. AI 서버(`/defect`)로 이미지 전송
5. 응답 결과에 따라 처리:
   - `{"label": "X"}` → 아두이노에 `X` 전송
   - 그 외 → 아두이노에 `GO` 전송

### 2️⃣ SNAP2 - 등급 판정

1. 아두이노로부터 `"SNAP2"` 신호 수신
2. 등급 판정용 카메라(CAM_IR2)로 이미지 촬영 (락 확보)
3. GCS `raw_grade/` 폴더에 이미지 업로드
4. Classify 서버(`/classify`)로 이미지 전송
5. 응답 `{"label": "A"}`에 따라 아두이노에 `RESULT:A` 전송

---

## 🤖 아두이노 제어 로직 (`aduino_final.ino`)

`aduino_final.ino`는 시스템의 물리적 동작을 제어하는 아두이노 스케치입니다. 라즈베리파이(cam.py)와 시리얼 통신을 통해 명령을 주고받으며, 센서 입력에 따라 모터와 서보 모터를 정밀하게 제어합니다.

### ⚙️ 주요 기능 및 구성

-   **IR 센서 입력**: 두 개의 IR 센서(`SENSOR1_PIN`, `SENSOR2_PIN`)를 사용하여 제품의 위치를 감지합니다.
    -   `SENSOR1_PIN`: 첫 번째 검사 지점(SNAP1)을 트리거하며, `cam.py`에 "SNAP1" 신호를 보냅니다.
    -   `SENSOR2_PIN`: 두 번째 검사 지점(SNAP2)을 트리거하며, `cam.py`에 "SNAP2" 신호를 보냅니다.
-   **DC 모터 제어**: 컨베이어 벨트의 구동을 담당하는 DC 모터의 속도와 방향을 제어합니다.
-   **서보 모터 제어**: 제품의 등급(A, B) 또는 불량(X) 판정 결과에 따라 제품을 분류하는 서보 모터를 제어합니다.
    -   `SERVO_ANGLE_A`, `SERVO_ANGLE_B`, `SERVO_ANGLE_X` 등의 각도 설정으로 정밀한 분류가 가능합니다.
-   **시리얼 통신**: `cam.py`로부터 `start`, `stop`, `GO`, `X`, `RESULT:A`, `RESULT:B` 등의 명령을 수신하고, 센서 감지 시 `SNAP1`, `SNAP2` 신호를 전송합니다.
-   **자동/수동 모드**: `start`/`stop` 명령을 통해 자동 제어 모드를 전환할 수 있습니다.
-   **강제 주행 윈도우**: 서버 응답 수신 후 일정 시간 동안 센서 입력을 무시하고 모터를 강제 주행시켜 다음 제품 처리를 원활하게 합니다.
-   **IR2 스킵 로직**: `SENSOR1_PIN`에서 불량(`X`)이 감지된 경우, 다음 `SENSOR2_PIN` 트리거를 건너뛰어 불필요한 검사를 방지합니다.

### 🤝 `cam.py`와의 상호작용

아두이노는 `cam.py`의 지시에 따라 제품의 이동을 제어하고, `cam.py`는 아두이노로부터 센서 신호를 받아 이미지 촬영 및 AI 서버 통신을 수행합니다. 이 두 스크립트의 유기적인 연동을 통해 자동 품질 검사 시스템이 동작합니다.

---

## ⚙️ 설정 및 구성

```python
# cam.py 상단 설정 값
PORT = '/dev/ttyACM0'
BAUD = 9600

SNAP1_KEYWORD = "SNAP1"
SNAP2_KEYWORD = "SNAP2"

URL_SNAP1 = 'http://34.64.178.127:8000/defect'
URL_SNAP2 = 'http://34.64.178.127:8100/classify'

GCS_KEY_PATH = "service-account.json"

# 이미지 업로드 버킷/폴더
BUCKET_NAME = "zezeone_image"
GCS_FOLDER_SNAP1 = "raw_defect"
GCS_FOLDER_SNAP2 = "raw_grade"

# 헬스체크 리포트 버킷/폴더
HEALTH_BUCKET_NAME = "zezeone_health"
HEALTH_FOLDER = "health_check"
GCS_STATUS_OBJECT = f"{HEALTH_FOLDER}/status.json"
HEALTH_INTERVAL = 60  # 헬스체크 주기 (초)

# 카메라 설정
CAM_IR1 = 2    # 결함용 카메라 인덱스
CAM_IR2 = 0    # 등급용 카메라 인덱스
RESOLUTION = (1280, 720) # 카메라 해상도
```

---

## 🧰 사전 준비 사항

### 📦 하드웨어
- Arduino Uno
- Raspberry Pi
- USB 카메라 2대(일반 캠, 현미경캠)
- 검사 장치 (조명, 컨베이어 등)

### 🧪 소프트웨어

#### 1. Python 패키지 설치
```bash
pip install pyserial requests opencv-python google-cloud-storage
```

#### 2. GCP 인증 파일
- `service-account.json` 파일을 `cam.py`와 동일한 경로에 배치해야 합니다.
- 해당 서비스 계정은 GCS 버킷(`zezeone_image`, `zezeone_health`)에 대한 쓰기 권한(`Storage Object Creator` 역할 등)이 필요합니다.

---

## 🚀 실행 방법

1. 하드웨어를 모두 연결하고 `cam.py`의 설정 값을 확인합니다.
2. 아래 명령어로 스크립트를 실행합니다.
```bash
python cam.py
```
3. 정상 실행 시, 아래와 같은 로그가 출력됩니다.
```
[*] Serial connected: /dev/ttyACM0
[Health] GCS uploaded gs://zezeone_health/health_check/status.json | {'ts': ..., 'ir1': 'ok', 'ir2': 'ok', 'defect': 'ok', 'classify': 'ok', 'overall': 'ok'}
[ARDUINO] SNAP1
[GCS] Uploaded: gs://zezeone_image/raw_defect/snap1_....jpg
[SNAP1] Normal → sent: GO
```

---

## 📡 헬스체크 기능

`cam.py`는 `HEALTH_INTERVAL` 주기로 백그라운드에서 다음 항목을 점검하고, 그 결과를 `zezeone_health` GCS 버킷에 JSON 파일로 업로드합니다.

| 항목 | 체크 방식 | 상태 |
|---|---|---|
| 결함 카메라 (CAM_IR1) | **실제 이미지 캡처** 시도 | `ok` / `fail` |
| 등급 카메라 (CAM_IR2) | **실제 이미지 캡처** 시도 | `ok` / `fail` |
| AI 서버 (결함) | `/health` 엔드포인트 GET 요청 | `ok` / `fail` |
| Classify 서버 (등급) | `/health` 엔드포인트 GET 요청 | `ok` / `fail` |
| **종합 상태** | 모든 항목이 `ok`일 경우 | `ok` / `fail` |

---

## 🔍 디렉토리 구조

```
raspi/
├── cam.py
├── README.md
└── aduino_final/
    └── aduino_final.ino
```

---

## 📝 기타 참고사항

- 이미지는 로컬 디스크에 저장되지 않고, 메모리상에서 인코딩되어 GCS 및 서버로 직접 전송됩니다. 이는 저장 공간을 절약하고 I/O 작업을 최소화합니다.
- **카메라 락(Lock)** 메커니즘 덕분에 헬스체크와 SNAP 신호 처리가 동시에 발생해도 카메라 자원 충돌 없이 안정적으로 동작합니다.
- `SNAP1`/`SNAP2` 키워드는 아두이노 스케치에서 `Serial.println()`으로 전송하는 문자열과 정확히 일치해야 합니다.

---

## 📬 문의

스마트팩토리 제제원팀