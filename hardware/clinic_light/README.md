# Clinic alarm light

A bare Arduino (Uno, Nano, Mega or similar) shows one clinic's status on its onboard LED, the small
"L" light next to pin 13. You only need the board and its USB cable.

| LED | Command | Meaning |
| --- | --- | --- |
| Two short pulses every 1.5 s | `OK` | The AI is working as validated |
| Slow blink, 1 s on, 1 s off | `DRIFT <clinic>` | The scans no longer look like the validated ones (drift_auc of 0.7 or more) |
| Fast blink | `ALARM <clinic>` | ClinicDrift has pulled the AI for review |
| Off | `OFF` | |

## Upload the sketch

1. Install the [Arduino IDE](https://www.arduino.cc/en/software) and plug the board in over USB.
2. **File > Open** `hardware/clinic_light/clinic_light.ino`.
3. **Tools > Board**: pick your board (e.g. *Arduino Uno*). A clone with a CH340 chip works as *Arduino Uno* or *Arduino Nano*. If a Nano upload fails, try *Processor > ATmega328P (Old Bootloader)*.
4. **Tools > Port**: pick the board's COM port (see below).
5. Click **Upload** (the right arrow). When it finishes, the LED flashes three times and then pulses (OK).

To check it, open **Tools > Serial Monitor** at 9600 baud with *Newline* line ending, and type
`ALARM US-WEAR-01`. The board replies `ACK ALARM US-WEAR-01` and the LED blinks fast.

## Finding the COM port on Windows

- In the Arduino IDE, **Tools > Port** lists it, e.g. `COM3 (Arduino Uno)`.
- Or open **Device Manager > Ports (COM & LPT)**: look for *Arduino Uno (COM3)* or *USB-SERIAL CH340 (COM5)*. Unplug the board and see which entry disappears.
- Or run `python -m serial.tools.list_ports -v`.

A CH340 clone that shows no port needs the CH340 driver from the chip maker (WCH).

## Run it

**Close the Serial Monitor first.** Only one program can hold the port, and opening it from Python
resets the board, so the first command arrives about 2 s after connecting.

```bash
pip install -r requirements-addons.txt                          # includes pyserial
python -m addons.status_light --replay --clinic US-WEAR-01 --delay 1.5
python -m addons.status_light --replay --clinic US-UPD-01        # harm alarm in week 13, no drift
python -m addons.status_light --state ALARM --clinic US-WEAR-01  # one command
python -m addons.run_demo --clinic US-WEAR-01 --light            # add-ons, then ALARM on the light
```

The port is found automatically; pass `--port COM3` to choose it. The replay prints each week and
sends it: for US-WEAR-01 that is OK for weeks 1 to 7, DRIFT in week 8 and ALARM from week 9.
Without pyserial or a board, the scripts print one `[light]` line and carry on without the light.
