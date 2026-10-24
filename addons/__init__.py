"""ClinicDrift add-ons: what happens after the monitor raises an alarm.

1. Cause finder: Gemini looks at the flagged clinic's scan statistics (and a few
   sample images) and suggests the most likely cause of the catch-rate drop.
2. Incident report: Gemini drafts an MHRA-style adverse incident report, tagged
   with MIT AI Risk Repository categories, for a human to review.
3. Spoken alert: ElevenLabs reads a short alert aloud for the clinic lead.

Every step works offline: without API keys (or if a call fails) the cause
finder uses rules, the report uses a template, and the voice step is skipped.
"""
