// ClinicDrift clinic alarm light: the board's own LED (LED_BUILTIN), driven over USB serial.
// Needs nothing but the board and its USB cable.
//
// Send one command per line at 9600 baud:
//   OK               slow heartbeat (two short pulses every 1.5 s): the AI is fine
//   DRIFT <clinic>   slow blink (1 s on, 1 s off): the scans no longer look validated
//   ALARM <clinic>   fast blink (10 a second): pull the AI for review
//   OFF              LED off
// Each command is answered with "ACK <command>" (or "ERR <line>" if unknown).

enum Mode { MODE_OFF, MODE_OK, MODE_DRIFT, MODE_ALARM };

Mode mode = MODE_OFF;
String line = "";
String clinic = "";
unsigned long modeStart = 0;

void setMode(Mode m) {
  mode = m;
  modeStart = millis();
}

bool ledOn(unsigned long t) {
  switch (mode) {
    case MODE_OK: {
      unsigned long p = t % 1500;  // pulse at 0-100 ms and 250-350 ms
      return p < 100 || (p >= 250 && p < 350);
    }
    case MODE_DRIFT:
      return (t % 2000) < 1000;
    case MODE_ALARM:
      return (t % 100) < 50;
    default:
      return false;
  }
}

void handle(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;
  int space = cmd.indexOf(' ');
  String word = space < 0 ? cmd : cmd.substring(0, space);
  String arg = space < 0 ? "" : cmd.substring(space + 1);
  word.toUpperCase();
  arg.trim();

  if (word == "OK") {
    setMode(MODE_OK);
  } else if (word == "DRIFT") {
    setMode(MODE_DRIFT);
  } else if (word == "ALARM") {
    setMode(MODE_ALARM);
  } else if (word == "OFF") {
    setMode(MODE_OFF);
  } else {
    Serial.print("ERR ");
    Serial.println(cmd);
    return;
  }
  clinic = arg;
  Serial.print("ACK ");
  Serial.print(word);
  if (arg.length() > 0) {
    Serial.print(' ');
    Serial.print(arg);
  }
  Serial.println();
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(9600);
  // Three quick flashes so you can see the sketch started.
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_BUILTIN, HIGH);
    delay(80);
    digitalWrite(LED_BUILTIN, LOW);
    delay(80);
  }
  Serial.println("CLINICDRIFT LIGHT READY (OK, DRIFT <clinic>, ALARM <clinic>, OFF)");
  setMode(MODE_OK);
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      handle(line);
      line = "";
    } else if (line.length() < 64) {
      line += c;
    }
  }
  digitalWrite(LED_BUILTIN, ledOn(millis() - modeStart) ? HIGH : LOW);
}
