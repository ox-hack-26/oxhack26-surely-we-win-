"""Show a clinic's status on an Arduino's onboard LED (sketch in hardware/clinic_light/).

    python -m addons.status_light --replay --clinic US-WEAR-01 --delay 1.5
    python -m addons.status_light --state ALARM --clinic US-WEAR-01
    python -m addons.status_light --replay --port COM3

The replay walks the clinic's weeks in order (sample-data/weekly.csv, else the alarm files) and
sends OK, DRIFT (drift_auc of 0.7 or more, so the estimate is no longer fully trusted) or ALARM
(the engine has pulled the AI). With no pyserial or no board it prints the weeks and does nothing
else, so the demo never breaks.
"""

import argparse
import csv
import time
from pathlib import Path

from . import config
from .alarm_schema import ALARMS_DIR

STATES = ("OK", "DRIFT", "ALARM", "OFF")
BAUD = 9600
DRIFT_LEVEL = 0.7  # the engine starts discounting its own estimate above this drift_auc
SAMPLE_DIR = config.ROOT.parent / "sample-data"
WEEKLY_CSV = SAMPLE_DIR / "weekly.csv"
SAMPLE_ALARMS_DIR = SAMPLE_DIR / "alarms"

# USB vendor ids of Arduino boards and the usual USB-serial chips on clones.
ARDUINO_VIDS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4, 0x239A}


def _load_serial():
    try:
        import serial  # pyserial
        import serial.tools.list_ports  # noqa: F401
    except ImportError:
        return None
    return serial


def find_port(list_ports=None):
    """Return the first serial port that looks like an Arduino, or None."""
    if list_ports is None:
        serial = _load_serial()
        if serial is None:
            return None
        list_ports = serial.tools.list_ports.comports
    for p in list_ports():
        desc = f"{getattr(p, 'description', '')} {getattr(p, 'manufacturer', '') or ''}".lower()
        if getattr(p, "vid", None) in ARDUINO_VIDS or any(k in desc for k in ("arduino", "ch340", "usb serial")):
            return p.device
    return None


class StatusLight:
    """The board, opened on first use. Every method is a no-op when there is no board."""

    def __init__(self, port=None, opener=None, list_ports=None, boot_wait=2.0):
        self.port = port
        self._opener = opener  # for tests: called as opener(port, baud) -> serial-like object
        self._list_ports = list_ports
        self.boot_wait = boot_wait
        self._conn = None
        self._tried = False
        self.warning = None

    def _warn(self, msg):
        if self.warning is None:
            self.warning = msg
            print(f"[light] {msg}; continuing without the light")

    def _connect(self):
        if self._tried:
            return self._conn
        self._tried = True
        opener = self._opener
        if opener is None:
            serial = _load_serial()
            if serial is None:
                self._warn("pyserial is not installed (pip install pyserial)")
                return None
            opener = lambda port, baud: serial.Serial(port, baud, timeout=1)  # noqa: E731
            if self._list_ports is None:
                self._list_ports = serial.tools.list_ports.comports
        port = self.port or (find_port(self._list_ports) if self._list_ports else None)
        if not port:
            self._warn("no Arduino found (plug it in, or pass --port COM3)")
            return None
        try:
            self._conn = opener(port, BAUD)
        except Exception as e:  # port busy (Serial Monitor open?) or gone
            self._warn(f"could not open {port}: {e}")
            return None
        self.port = port
        time.sleep(self.boot_wait)  # opening the port resets the board
        banner = self._read_line()
        print(f"[light] connected on {port}" + (f": {banner}" if banner else ""))
        return self._conn

    def _read_line(self):
        try:
            return self._conn.readline().decode("ascii", "replace").strip()
        except Exception:
            return ""

    def send_state(self, state, clinic=None):
        """Send OK, DRIFT, ALARM or OFF; return the board's reply ("ACK ...") or None."""
        state = state.upper()
        if state not in STATES:
            raise ValueError(f"state must be one of {STATES}, not {state!r}")
        if self._connect() is None:
            return None
        cmd = f"{state} {clinic}" if clinic and state in ("DRIFT", "ALARM") else state
        try:
            self._conn.write((cmd + "\n").encode("ascii"))
            self._conn.flush()
        except Exception as e:
            self._warn(f"lost the board: {e}")
            self._conn = None
            return None
        return self._read_line() or None

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None


_default = None


def send_state(state, clinic=None, port=None):
    """Send a state to the default board, connecting once."""
    global _default
    if _default is None or (port and port != _default.port):
        _default = StatusLight(port)
    return _default.send_state(state, clinic)


def week_states(clinic, weekly_csv=WEEKLY_CSV, alarms_dir=None):
    """[(week, week_start, state, reason)] for one clinic, in week order."""
    weekly_csv = Path(weekly_csv)
    if weekly_csv.exists():
        rows = []
        with open(weekly_csv, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["clinic_id"] != clinic:
                    continue
                drift = float(r["drift_auc"]) if r.get("drift_auc") else 0.0
                if r.get("alarm", "").strip().lower() == "true":
                    state, reason = "ALARM", r.get("alarm_reason") or None
                elif drift >= DRIFT_LEVEL:
                    state, reason = "DRIFT", f"drift {drift:.2f}"
                else:
                    state, reason = "OK", None
                rows.append((int(r["week"]), r.get("week_start", ""), state, reason))
        if rows:
            return sorted(rows)
    # No weekly table: OK until the clinic's first alarm file, ALARM from then on.
    folder = Path(alarms_dir) if alarms_dir else (ALARMS_DIR if any(ALARMS_DIR.glob("*.json")) else SAMPLE_ALARMS_DIR)
    weeks = sorted(int(p.stem.rsplit("week", 1)[1]) for p in folder.glob(f"{clinic}_week*.json"))
    if not weeks:
        return []
    return [(w, "", "ALARM" if w >= weeks[0] else "OK", None) for w in range(1, max(weeks[-1], 20) + 1)]


def replay(clinic, delay=1.5, light=None, weekly_csv=WEEKLY_CSV):
    """Step through the clinic's weeks, printing each and sending it to the light."""
    light = light or StatusLight()
    rows = week_states(clinic, weekly_csv)
    if not rows:
        print(f"No weeks for {clinic}")
    for i, (week, start, state, reason) in enumerate(rows):
        ack = light.send_state(state, clinic)
        print(f"week {week:2d} {start:10s} {clinic}: {state}" + (f" ({reason})" if reason else "") + (f"  <- {ack}" if ack else ""))
        if delay and i < len(rows) - 1:
            time.sleep(delay)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drive the Arduino clinic light.")
    parser.add_argument("--port", help="serial port, e.g. COM3 (default: auto-detect)")
    parser.add_argument("--clinic", default="US-WEAR-01")
    parser.add_argument("--replay", action="store_true", help="step through the clinic's 20 weeks")
    parser.add_argument("--delay", type=float, default=1.5, help="seconds per week in --replay")
    parser.add_argument("--state", choices=STATES, help="send one state and exit")
    args = parser.parse_args()

    light = StatusLight(args.port)
    if args.replay:
        replay(args.clinic, args.delay, light)
    elif args.state:
        print(light.send_state(args.state, args.clinic) or "(no reply)")
    else:
        parser.print_help()
    light.close()
