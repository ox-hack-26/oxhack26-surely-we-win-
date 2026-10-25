"""The dashboard's look, matched to the 3D web app's design system (web/MASTER.md): a dark instrument
console, colour only for data (blue ClinicDrift, orange expert grades, aqua drift, amber the AI's own
estimate, red alarms only), Instrument Sans for words and IBM Plex Mono for numbers, flat panels with
hairline borders. apply() styles the page and makes every Plotly chart use the same palette."""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

GROUND, PANEL, PANEL_2, PANEL_3 = "#0d0d0d", "#1a1a19", "#232321", "#2c2c2a"
HAIRLINE, HAIRLINE_STRONG = "rgba(255,255,255,0.10)", "rgba(255,255,255,0.28)"
INK, INK_2, MUTED = "#f0efec", "#c3c2b7", "#898781"
BELIEF, GRADES, DRIFT, ESTIMATE, ALARM = "#3987e5", "#d95926", "#199e70", "#c98500", "#d03b3b"
BELIEF_BAND = "rgba(57,135,229,0.20)"
POLICY_COLOURS = {"ClinicDrift": BELIEF, "wait for grades": GRADES, "watch drift": DRIFT, "watch estimate": ESTIMATE}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Instrument+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"], .stApp, .stMarkdown, p, label, li {{ font-family: "Instrument Sans", "Segoe UI", system-ui, sans-serif; }}
.stApp {{ background: {GROUND}; color: {INK}; }}
.block-container {{ padding-top: 1.6rem; max-width: 1400px; }}
h1, h2, h3 {{ font-family: "Instrument Sans", "Segoe UI", sans-serif !important; letter-spacing: -0.01em; color: {INK} !important; }}
h1 {{ font-weight: 600 !important; font-size: 2rem !important; }}
h2, h3 {{ font-weight: 600 !important; font-size: 1.15rem !important; }}
[data-testid="stCaptionContainer"], .stCaption {{ color: {MUTED} !important; }}
hr {{ border-color: {HAIRLINE} !important; }}

/* Sidebar: the instrument's control panel. */
[data-testid="stSidebar"] {{ background: {PANEL}; border-right: 1px solid {HAIRLINE}; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ font-size: 1rem !important; }}
[data-testid="stSidebar"] label p {{ font-size: 0.82rem; color: {INK_2}; }}

/* Readouts: flat panels, hairline border, mono numbers. */
div[data-testid="stMetric"] {{ background: {PANEL}; border: 1px solid {HAIRLINE}; border-radius: 6px; padding: 14px 16px; }}
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {{ color: {MUTED} !important; font-size: 0.72rem; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; white-space: normal !important; }}
div[data-testid="stMetric"] [data-testid="stMetricLabel"] * {{ overflow: visible !important; text-overflow: clip !important; white-space: normal !important; }}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ font-family: "IBM Plex Mono", Consolas, monospace; font-weight: 500; color: {INK} !important; font-size: 1.4rem; }}
div[data-testid="stMetric"] [data-testid="stMetricValue"] * {{ overflow: visible !important; text-overflow: clip !important; white-space: normal !important; }}

/* Notices: a panel with a coloured edge, never a coloured block. */
div[data-testid="stAlert"] {{ background: {PANEL} !important; border: 1px solid {HAIRLINE}; border-left: 3px solid {MUTED}; border-radius: 6px; color: {INK_2} !important; }}
div[data-testid="stAlert"] > div, [data-testid="stAlertContainer"] {{ background: transparent !important; color: {INK_2} !important; }}
div[data-testid="stAlert"] p {{ color: {INK_2} !important; }}
div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {{ border-left-color: {ALARM}; }}
div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {{ border-left-color: {BELIEF}; }}
div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {{ border-left-color: {DRIFT}; }}
div[data-testid="stAlert"] svg {{ display: none; }}

/* Controls. */
div[data-baseweb="select"] > div, .stTextInput input {{ background: {PANEL_2} !important; border-color: {HAIRLINE} !important; border-radius: 6px !important; }}
.stSlider [data-baseweb="slider"] [role="slider"] {{ background: {INK} !important; box-shadow: none !important; }}
[data-testid="stTickBarMin"], [data-testid="stTickBarMax"], .stSlider [data-testid="stThumbValue"] {{ font-family: "IBM Plex Mono", monospace; color: {INK_2} !important; }}
.stButton button {{ background: transparent; border: 1px solid {HAIRLINE}; border-radius: 6px; color: {INK}; }}
.stButton button:hover {{ background: {PANEL_2}; border-color: {HAIRLINE_STRONG}; color: {INK}; }}
[data-testid="stDataFrame"] {{ border: 1px solid {HAIRLINE}; border-radius: 6px; }}
code {{ font-family: "IBM Plex Mono", monospace !important; color: {INK_2} !important; background: {PANEL_2} !important; }}
</style>
"""


def _template() -> go.layout.Template:
    axis = dict(gridcolor=PANEL_3, linecolor="#383835", zerolinecolor="#383835",
                tickfont=dict(family="IBM Plex Mono, monospace", size=11, color=MUTED),
                title=dict(font=dict(size=12, color=MUTED)))
    return go.layout.Template(layout=dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Instrument Sans, Segoe UI, sans-serif", size=12, color=INK_2),
        colorway=[BELIEF, GRADES, DRIFT, ESTIMATE],
        xaxis=axis, yaxis=axis,
        legend=dict(font=dict(color=INK_2), bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=PANEL_2, bordercolor=HAIRLINE_STRONG, font=dict(color=INK, family="IBM Plex Mono, monospace")),
        title=dict(font=dict(size=14, color=INK)),
    ))


def apply() -> None:
    """Style the page and set the default Plotly template. Call once, right after set_page_config."""
    pio.templates["clinicdrift"] = _template()
    pio.templates.default = "plotly_dark+clinicdrift"
    st.markdown(_CSS, unsafe_allow_html=True)
