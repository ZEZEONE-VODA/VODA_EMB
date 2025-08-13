#include <Servo.h>

/* -------- PIN 설정 -------- */
const int SENSOR1_PIN   = A0;   // IR 센서 1 (촬영만)
const int SENSOR2_PIN   = A5;   // IR 센서 2 (촬영 + 서버 업로드)
const int MOTOR_PWM_PIN = 11;   // DC 모터 PWM (Timer2)
const int MOTOR_DIR_PIN = 13;   // DC 모터 방향
#define  PIN_SERVO       9      // 서보모터 (Timer1)

/* -------- 서보 각도 -------- */
const int SERVO_ANGLE_A    = 60;
const int SERVO_ANGLE_B    = 30;
const int SERVO_ANGLE_X    = 0;   // 결함
const int SERVO_ANGLE_IDLE = 0;

/* -------- 상태 변수 -------- */
bool autoMode      = true;    // 자동/정지 모드
bool waitingResult = false;   // 서버 응답 대기 중인지
bool snapFlag1     = false;   // IR1 재트리거 방지
bool snapFlag2     = false;   // IR2 재트리거 방지
bool skipIR2       = false;   // IR1에서 X면 다음 IR2 스킵
bool sawIR2LowWhileSkipping = false; // skip 해제 조건(LOW→HIGH) 감시

// 결과 수신 후, 일정 시간 센서 무시하고 강제 주행
bool          forceRun      = false;
unsigned long forceRunUntil = 0;
const unsigned long FORCE_MS = 800; // 필요시 500~1500으로 조절

Servo sorter;
int   lastServoAngle = -1;    // 마지막 서보 위치

/* -------- 유틸 -------- */
void startMotor(uint8_t spd = 90) { analogWrite(MOTOR_PWM_PIN, spd); }
void stopMotor()                  { analogWrite(MOTOR_PWM_PIN, 0);  }

void moveServoOnce(int target, int hold_ms = 400) {
  if (lastServoAngle == target) return;     // 중복 방지
  sorter.attach(PIN_SERVO);
  sorter.write(target);
  delay(hold_ms);
  sorter.detach();                          // 지터 방지
  lastServoAngle = target;
}

/* -------- SETUP -------- */
void setup() {
  Serial.begin(9600);

  pinMode(SENSOR1_PIN, INPUT);
  pinMode(SENSOR2_PIN, INPUT);
  pinMode(MOTOR_PWM_PIN, OUTPUT);
  pinMode(MOTOR_DIR_PIN, OUTPUT);

  digitalWrite(MOTOR_DIR_PIN, HIGH);        // 필요 시 LOW로 변경
  startMotor();                             // 초기 가동
  moveServoOnce(SERVO_ANGLE_IDLE, 300);

  Serial.println(F("start / stop / RESULT:A|B / X / GO"));
}

/* -------- LOOP -------- */
void loop() {
  /* ----- PC(라즈베리파이) → Arduino 시리얼 명령 ----- */
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    Serial.print(F("수신: '")); Serial.print(cmd); Serial.println("'");

    // 수동 제어
    if (cmd == "start") {
      autoMode = true;
      waitingResult = false;
      snapFlag1 = snapFlag2 = false;
      skipIR2 = false;
      sawIR2LowWhileSkipping = false;
      startMotor();
      Serial.println(F("자동제어모드 ON"));
    }
    else if (cmd == "stop") {
      autoMode = false;
      stopMotor();
      Serial.println(F("강제정지모드 ON"));
    }
    // 서버 응답 처리
    else if (cmd == "GO") {
      Serial.println(F("GO → 모터 재가동"));
      startMotor();
      waitingResult = false;
      forceRun = true; forceRunUntil = millis() + FORCE_MS;
    }
    else if (cmd == "X") {
      Serial.println(F("X → 불량 분류(서보 이동)"));
      moveServoOnce(SERVO_ANGLE_X);
      startMotor();
      waitingResult = false;
      skipIR2 = true;                    // 다음 IR2 스킵
      sawIR2LowWhileSkipping = false;    // LOW 감시 시작
      forceRun = true; forceRunUntil = millis() + FORCE_MS;
    }
    else if (cmd.startsWith("RESULT:")) {
      String grade = cmd.substring(7);
      if (grade == "A") {
        Serial.println(F("A 등급 → 서보 60°"));
        moveServoOnce(SERVO_ANGLE_A);
      } else if (grade == "B") {
        Serial.println(F("B 등급 → 서보 40°"));
        moveServoOnce(SERVO_ANGLE_B);
      } else {
        Serial.println(F("알 수 없는 등급"));
      }
      startMotor();
      waitingResult = false;
      forceRun = true; forceRunUntil = millis() + FORCE_MS;
    }
    else {
      Serial.println(F("start/stop/RESULT:A|B/X/GO 만 허용"));
    }
  }

  /* ----- 강제 주행 윈도우(센서 무시) ----- */
  if (autoMode && forceRun) {
    if (millis() < forceRunUntil) {
      startMotor();       // 계속 돌려줌
      delay(20);
      return;             // 센서 로직 완전히 스킵
    } else {
      forceRun = false;
    }
  }

  /* ----- 자동 제어 / 센서 로직 ----- */
  if (autoMode && !waitingResult) {
    int v1 = digitalRead(SENSOR1_PIN);
    int v2 = digitalRead(SENSOR2_PIN);

    /* IR1 트리거 (촬영만) */
    if (v1 == LOW && !snapFlag1 && v2 == HIGH) {
      stopMotor();
      Serial.println(F("IR1 LOW ⇒ 레일 정지 / SNAP1"));
      delay(1000);
      Serial.println(F("SNAP1"));
      snapFlag1 = true;
      waitingResult = true;   // 응답 올 때까지 센서 무시
    }
    if (v1 == HIGH && snapFlag1) snapFlag1 = false;

    /* skipIR2 해제 로직: IR2가 LOW를 한번 거쳐 HIGH로 돌아오면 해제 */
    if (skipIR2) {
      if (v2 == LOW)  sawIR2LowWhileSkipping = true;
      if (sawIR2LowWhileSkipping && v2 == HIGH) {
        skipIR2 = false;
        sawIR2LowWhileSkipping = false;
        Serial.println(F("skipIR2 해제(LOW→HIGH 통과)"));
      }
    }

    /* IR2 트리거 (촬영 + 서버) : skipIR2가 false일 때만 */
    if (v2 == LOW && !snapFlag2 && !skipIR2) {
      stopMotor();
      Serial.println(F("IR2 LOW ⇒ 레일 정지 / SNAP2"));
      delay(2500);
      Serial.println(F("SNAP2"));
      snapFlag2 = true;
      waitingResult = true;
    }
    if (v2 == HIGH && snapFlag2) snapFlag2 = false;

    /* IR1·IR2 모두 HIGH → 이동 유지 */
    if (v1 == HIGH && v2 == HIGH && !waitingResult) {
      startMotor();
      // 여기서는 skipIR2를 건드리지 않음(LOW→HIGH로만 해제)
    }
  }

  delay(50);
}
