"""Short spoken alert for the clinic lead, voiced with ElevenLabs."""

from typing import Optional

from . import config
from .alarm_schema import Alarm
from .cause_finder import Cause


def alert_script(alarm: Alarm, cause: Cause) -> str:
    """Alert text, short enough to read in under 25 seconds."""
    first = cause.recommended_checks[0].rstrip(".") if cause.recommended_checks else "review this week's scans"
    return (
        f"ClinicDrift alert for clinic {alarm.clinic_id}. "
        f"The eye screening AI's estimated catch rate has dropped from "
        f"{alarm.baseline_sensitivity:.0%} to {alarm.est_sensitivity:.0%} this week. "
        f"The likely cause is {cause.category}. "
        f"We recommend pausing the AI at this clinic for review. "
        f"First step: {first}. "
        f"A draft incident report is ready on the dashboard."
    )


def speak(text: str, filename: str) -> Optional[str]:
    """Save `text` as an mp3 in the output folder. Returns the path, or None."""
    if not config.ELEVENLABS_API_KEY:
        return None
    try:
        from elevenlabs.client import ElevenLabs

        audio = ElevenLabs(api_key=config.ELEVENLABS_API_KEY).text_to_speech.convert(
            voice_id=config.ELEVENLABS_VOICE_ID,
            text=text,
            model_id=config.ELEVENLABS_MODEL,
            output_format="mp3_44100_128",
        )
        path = config.out_dir() / filename
        with open(path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        return str(path)
    except Exception as e:
        print(f"[elevenlabs] skipped: {type(e).__name__}: {e}")
        return None
