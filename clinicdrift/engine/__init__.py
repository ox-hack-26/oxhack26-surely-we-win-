"""Tejas: replay deploy scans as clinic-weeks, estimate each clinic's catch rate from images alone,
decide when to raise the alarm, and backtest against the expert grades.

Reads processed/scans.parquet; writes processed/stream.parquet, weekly.parquet and alarms/ in the
format addons/alarm_schema.py reads (see docs/handoffs.md).
"""
