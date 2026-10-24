"""Offline tests for the Arduino clinic light bridge, with a fake serial port."""

from types import SimpleNamespace

import pytest

from addons import status_light
from addons.status_light import StatusLight, find_port, replay, week_states


class FakeSerial:
    """Answers like clinic_light.ino: a banner on open, then ACK per command."""

    def __init__(self, port, baud):
        self.port, self.baud = port, baud
        self.sent = []
        self.replies = [b"CLINICDRIFT LIGHT READY\r\n"]
        self.closed = False

    def write(self, data):
        cmd = data.decode("ascii").strip()
        self.sent.append(cmd)
        word, _, arg = cmd.partition(" ")
        self.replies.append(f"ACK {word} {arg}".strip().encode() + b"\r\n")

    def flush(self):
        pass

    def readline(self):
        return self.replies.pop(0) if self.replies else b""

    def close(self):
        self.closed = True


@pytest.fixture
def board():
    opened = []

    def opener(port, baud):
        opened.append(FakeSerial(port, baud))
        return opened[-1]

    return opener, opened


def test_sends_commands_and_reads_acks(board):
    opener, opened = board
    light = StatusLight("COM3", opener=opener, boot_wait=0)
    assert light.send_state("alarm", "US-WEAR-01") == "ACK ALARM US-WEAR-01"
    assert light.send_state("OK", "US-WEAR-01") == "ACK OK"
    assert light.send_state("OFF") == "ACK OFF"
    assert len(opened) == 1 and opened[0].baud == 9600
    assert opened[0].sent == ["ALARM US-WEAR-01", "OK", "OFF"]
    light.close()
    assert opened[0].closed


def test_rejects_unknown_state(board):
    with pytest.raises(ValueError):
        StatusLight("COM3", opener=board[0], boot_wait=0).send_state("BLUE")


def test_auto_detects_arduino_port(board):
    ports = lambda: [  # noqa: E731
        SimpleNamespace(device="COM1", vid=None, description="Communications Port", manufacturer=None),
        SimpleNamespace(device="COM5", vid=0x2341, description="Arduino Uno (COM5)", manufacturer="Arduino LLC"),
    ]
    assert find_port(ports) == "COM5"
    light = StatusLight(opener=board[0], list_ports=ports, boot_wait=0)
    assert light.send_state("DRIFT", "SW-MES-01") == "ACK DRIFT SW-MES-01"
    assert light.port == "COM5"


def test_no_board_is_a_quiet_noop(board, capsys):
    light = StatusLight(opener=board[0], list_ports=lambda: [], boot_wait=0)
    assert light.send_state("ALARM", "US-WEAR-01") is None
    assert light.send_state("OK") is None
    assert board[1] == []
    assert capsys.readouterr().out.count("[light]") == 1


def test_missing_pyserial_is_a_quiet_noop(monkeypatch, capsys):
    monkeypatch.setattr(status_light, "_load_serial", lambda: None)
    light = StatusLight(boot_wait=0)
    assert light.send_state("ALARM", "US-WEAR-01") is None
    assert light.send_state("ALARM", "US-WEAR-01") is None
    out = capsys.readouterr().out
    assert out.count("[light]") == 1 and "pyserial" in out


def test_busy_port_is_a_quiet_noop(capsys):
    def opener(port, baud):
        raise OSError("access denied")

    light = StatusLight("COM3", opener=opener, boot_wait=0)
    assert light.send_state("OK") is None
    assert "could not open COM3" in capsys.readouterr().out


def test_week_states_follow_the_engine():
    states = {w: s for w, _, s, _ in week_states("US-WEAR-01")}
    assert [states[w] for w in range(1, 8)] == ["OK"] * 7
    assert states[8] == "DRIFT" and states[9] == "ALARM" and states[20] == "ALARM"
    upd = {w: s for w, _, s, _ in week_states("US-UPD-01")}
    assert set(upd[w] for w in range(1, 13)) == {"OK"} and upd[13] == "ALARM"
    assert set(s for _, _, s, _ in week_states("US-EYE-01")) <= {"OK", "DRIFT"}


def test_week_states_fall_back_to_alarm_files(tmp_path):
    (tmp_path / "US-WEAR-01_week09.json").write_text("{}")
    rows = week_states("US-WEAR-01", tmp_path / "missing.csv", tmp_path)
    assert [s for _, _, s, _ in rows[:9]] == ["OK"] * 8 + ["ALARM"]
    assert len(rows) == 20


def test_replay_sends_each_week_in_order(board, capsys):
    opener, opened = board
    rows = replay("US-WEAR-01", delay=0, light=StatusLight("COM3", opener=opener, boot_wait=0))
    assert len(rows) == 20
    assert opened[0].sent[7:9] == ["DRIFT US-WEAR-01", "ALARM US-WEAR-01"]
    out = capsys.readouterr().out
    assert "week  9" in out and "ALARM (drift)" in out
