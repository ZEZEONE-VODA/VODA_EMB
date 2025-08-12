# 🎥 cam.py - 자동 품질 검사 컨트롤러

Python OpenCV Serial GoogleCloud FastAPI

---

## 🎯 프로젝트 개요

`cam.py`는 아두이노와 라즈베리파이, AI 서버와의 통신을 통해 자동 품질 검사 프로세스를 제어하는 메인 컨트롤러입니다.  
두 대의 카메라(일반 카메라, 현미경 카메라)를 사용하여 **결함 검사(SNAP1)**와 **등급 판정(SNAP2)**을 수행하며,  
촬영된 이미지는 Google Cloud Storage(GCS)에 자동 백업되고, 결과에 따라 아두이노를 통해 후속 제어가 이뤄집니다.

또한, 시스템 주요 요소들(카메라, 서버)의 상태를 정기적으로 점검하는 **헬스체크 기능**을 제공하여 안정적인 스마트팩토리 운영을 지원합니다.

---

## ✨ 주요 기능

- **SNAP1: 결함 검사**
  - 일반 카메라로 촬영된 이미지를 AI 서버로 전송
  - `{"label": "X"}` → 불량 (X), 정상 시 → GO 신호 전송

- **SNAP2: 등급 판정**
  - 현미경 카메라로 촬영된 이미지를 Rule 기반 서버로 전송
  - `{"label": "A"}` → 아두이노로 `RESULT:A` 형식으로 전송

- **GCS 업로드**
  - SNAP1 → `raw_defect/` 폴더
  - SNAP2 → `raw_grade/` 폴더

- **헬스체크**
  - 카메라 및 서버 상태를 주기적으로 점검하고, 결과를 프론트엔드로 전송

---

## 🧭 시스템 워크플로우

### 1️⃣ SNAP1 - 결함 검사

1. 아두이노로부터 `"SNAP1"` 신호 수신
2. 일반 카메라로 이미지 촬영
3. GCS `raw_defect/`에 이미지 업로드
4. AI 서버(`/defect`)로 전송
5. 응답 결과:
   - `"label": "X"` → 아두이노에 `X` 전송
   - 그 외 → 아두이노에 `GO` 전송

### 2️⃣ SNAP2 - 등급 판정

1. 아두이노로부터 `"SNAP2"` 신호 수신
2. 현미경 카메라로 이미지 촬영
3. GCS `raw_grade/`에 이미지 업로드
4. Classify 서버(`/classify`)로 전송
5. 응답 예시: `{ "label": "A" }` → 아두이노에 `RESULT:A` 전송

---

## ⚙️ 설정 및 구성

```python
# 기본 설정 (cam.py 상단)
PORT = '/dev/ttyACM0'             # 아두이노 연결 포트
BAUD = 9600                       # 시리얼 통신 속도

SNAP1_KEYWORD = "SNAP1"
SNAP2_KEYWORD = "SNAP2"

URL_SNAP1 = "http://<AI 서버 IP>:8000/defect"
URL_SNAP2 = "http://<Rule 서버 IP>:8100/classify"

GCS_KEY_PATH = "service-account.json"
BUCKET_NAME = "zezeone_images"
GCS_FOLDER_SNAP1 = "raw_defect"
GCS_FOLDER_SNAP2 = "raw_grade"

CAM_IR1 = 0  # 일반 카메라 인덱스
CAM_IR2 = 1  # 현미경 카메라 인덱스

FRONT_HEALTHCHECK_URL = "http://<FRONT-END IP>/health"
```

---

## 🧰 사전 준비 사항

### 📦 하드웨어
- Arduino Uno
- Raspberry Pi
- USB 카메라 2대 (일반, 현미경)
- 조명, 컨베이어 등 검사 장치

### 🧪 소프트웨어

#### 1. Python 패키지 설치
```bash
pip install pyserial requests opencv-python google-cloud-storage
```

#### 2. GCP 인증 파일
- `service-account.json` 파일을 루트 경로에 배치
- GCS에 업로드 권한이 있어야 함

---

## 🚀 실행 방법

1. 하드웨어를 모두 연결하고 설정 값을 확인합니다.
2. 아래 명령어로 실행:
```bash
python cam.py
```
3. 정상 실행 시, 아래 로그들이 출력됩니다:
```
[INFO] Serial 연결 완료
[INFO] SNAP1 신호 대기 중...
[INFO] 카메라 상태 점검 중...
```

---

## 📡 헬스체크 기능

cam.py는 주기적으로 다음 요소를 점검하고 프론트엔드로 결과를 전송합니다:

| 항목             | 체크 방식                     |
|------------------|-------------------------------|
| 일반 카메라       | OpenCV VideoCapture 확인       |
| 현미경 카메라     | OpenCV VideoCapture 확인       |
| AI 서버           | URL_SNAP1 응답 확인            |
| classify 서버         | URL_SNAP2 응답 확인            |

---

## 🔍 디렉토리 구조 예시

```
cam_controller/
├── cam.py
├── service-account.json
├── captured/
│   ├── defect_20250801_103000.jpg
│   └── grade_20250801_104500.jpg
└── README.md
```

---

## 📝 기타 참고사항

- 이미지 파일은 전송 후 자동 삭제되어 저장 공간을 최소화합니다.
- 프론트엔드에서 실시간 시스템 상태를 확인할 수 있도록 push 방식으로 전송합니다.
- SNAP1/2 키워드는 아두이노 코드와 일치해야 합니다.

---

## 📬 문의

스마트팩토리 프로젝트 개발팀  
이메일: contact@smartfactory.local
