# VODA_EMB — cam.py 자동 품질 검사 컨트롤러 (v2)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-green.svg)](https://opencv.org/)
[![Google Cloud](https://img.shields.io/badge/Google_Cloud_Storage-blue.svg)](https://cloud.google.com/storage)
[![Hardware](https://img.shields.io/badge/Arduino/RaspberryPi-orange.svg)](https://www.arduino.cc/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🔎 개요

**VODA_EMB**는 아두이노와 라즈베리파이를 기반으로 한 **스마트 팩토리 임베디드 컨트롤러**입니다.  
`cam.py`를 통해 **SNAP1(결함 검사)** / **SNAP2(등급 판정)** 프로세스를 제어하고,  
AI/Rule 서버와 통신하며 Google Cloud Storage(GCS) 업로드 및 **헬스체크**를 수행합니다.  

---

## ✨ 주요 기능

- **SNAP1 결함 검사**: 일반 카메라(CAM_IR1) 촬영 → AI 서버 `/defect` 전송 → 결과(`GO`/`X`)를 아두이노에 전달
- **SNAP2 등급 판정**: 현미경 카메라(CAM_IR2) 촬영 → Rule 서버 `/classify` 전송 → 결과(`RESULT:A/B`)를 아두이노에 전달
- **GCS 연동**: SNAP1 이미지는 `raw_defect/`, SNAP2 이미지는 `raw_grade/` 업로드
- **헬스체크**: 카메라/서버 상태 점검 후 `health_check/status.json` 업로드
- **안정성**: `threading.Lock` 기반 카메라 락으로 동시 접근 충돌 방지

---

## 🧭 워크플로우

### SNAP1 — 결함 검사
1. 아두이노에서 `"SNAP1"` 신호 수신  
2. CAM_IR1 촬영 (락 확보)  
3. GCS `raw_defect/` 업로드  
4. AI 서버 `/defect` 전송  
5. 결과 처리  
   - `{"label": "X"}` → 아두이노에 `X` 전송  
   - 정상 → 아두이노에 `GO` 전송  

### SNAP2 — 등급 판정
1. 아두이노에서 `"SNAP2"` 신호 수신  
2. CAM_IR2 촬영 (락 확보)  
3. GCS `raw_grade/` 업로드  
4. Rule 서버 `/classify` 전송  
5. 응답 `{"label": "A"}` → 아두이노에 `RESULT:A` 전송  

---

## 🤖 아두이노 로직 (`aduino_final.ino`)

- **IR 센서**: SENSOR1 → SNAP1 트리거, SENSOR2 → SNAP2 트리거  
- **DC 모터**: 컨베이어벨트 구동  
- **서보 모터**: `RESULT:A/B` 및 `X` 값에 따라 제품 분류  
- **시리얼 통신**: `GO`, `X`, `RESULT:A` 등 명령 처리  
- **IR2 스킵 로직**: SNAP1에서 `X` 감지 시 SNAP2 검사 생략  

---

## ⚙️ 설정

`cam.py` 주요 설정값은 환경변수 또는 코드 상단에서 지정합니다.

```bash
# .env 예시
PORT=/dev/ttyACM0
BAUD=9600

URL_SNAP1=http://<AI_SERVER>:8000/defect
URL_SNAP2=http://<RULE_SERVER>:8100/classify

GCS_KEY_PATH=service-account.json
BUCKET_NAME=zezeone_image
HEALTH_BUCKET_NAME=zezeone_health
HEALTH_INTERVAL=60
CAM_IR1=2
CAM_IR2=0
RESOLUTION=1280x720
```

---

## 🚀 실행 방법

### 개발 모드
```bash
pip install -r requirements.txt
python cam.py
```

### 운영 모드 (systemd 예시)
```bash
# /etc/systemd/system/voda-emb.service
[Unit]
Description=VODA_EMB cam.py Controller
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/raspi/cam.py
WorkingDirectory=/home/pi/raspi
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable voda-emb
sudo systemctl start voda-emb
```

---

## 📡 헬스체크

주기적으로 다음 항목을 점검하고 GCS에 JSON 업로드합니다.

| 항목 | 체크 방식 | 상태 |
| --- | --- | --- |
| 결함 카메라 | 이미지 캡처 시도 | `ok` / `fail` |
| 등급 카메라 | 이미지 캡처 시도 | `ok` / `fail` |
| AI 서버 | `/health` 호출 | `ok` / `fail` |
| Rule 서버 | `/health` 호출 | `ok` / `fail` |
| 종합 상태 | 전체가 `ok`일 경우 | `ok` / `fail` |

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

## 📝 참고 사항

- 이미지는 로컬에 저장하지 않고 메모리상 인코딩 후 **직접 전송** → I/O 최소화  
- 카메라 락으로 **헬스체크와 SNAP 신호 동시 처리** 시에도 안정성 확보  
- 아두이노 코드와 cam.py의 `"SNAP1"`, `"SNAP2"` 키워드는 반드시 일치해야 함  

---

## 📬 문의

- GitHub Issues: [VODA_EMB](https://github.com/KSEB-04-2025/VODA_EMB/issues)  
- 스마트팩토리 ZEZE ONE 팀
