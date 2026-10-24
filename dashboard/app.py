"""Run with: streamlit run app.py"""
import json
import streamlit as st
from dotenv import load_dotenv
from clinicdrift.storage import load_weekly, mode
from clinicdrift.contracts import visible_weekly
from clinicdrift.decisions import demo_decision
from clinicdrift.charts import performance_chart
from clinicdrift.replay import alert_json

load_dotenv()
st.set_page_config(page_title='ClinicDrift | OxHack 2026',page_icon='👁️',layout='wide')
st.markdown('''<style>
.block-container {padding-top:1.6rem; max-width:1350px;}
h1 {letter-spacing:-.04em;}
/* Respect Streamlit's current dark/light theme: never put white text on white cards. */
div[data-testid="stMetric"] {
  background:rgba(128,128,128,0.12);
  padding:14px;
  border-radius:12px;
  border:1px solid rgba(128,128,128,0.28);
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
  color:var(--text-color) !important;
}
</style>''', unsafe_allow_html=True)
st.title('ClinicDrift')
st.caption('OxHack 2026 · HRT: Predictions & Decision Making · Retinal AI safety monitoring')
st.warning('RESEARCH PROTOTYPE · Synthetic records are fictional, not clinical findings. Decisions are illustrative and require human review.')
try: weekly,origin=load_weekly()
except (RuntimeError,ValueError) as exc:
    st.error(str(exc));st.stop()
st.caption(f'Data mode: **{origin}** · Reference training source: EyePACS (US) · Deployment datasets are NOT actual clinics')
with st.sidebar:
    st.header('Clinic replay')
    clinic=st.selectbox('Deployment dataset',sorted(weekly.clinic_id.unique()))
    selected=weekly[weekly.clinic_id==clinic].sort_values('clinic_week')
    replay_week=st.slider('Replay through week',int(selected.clinic_week.min()),int(selected.clinic_week.max()),int(selected.clinic_week.max()))
    st.divider()
    st.header('Decision assumptions')
    review_cost=st.slider('Review cost (illustrative units)',0,3000,500,50)
    missed_cost=st.slider('Missed-case loss (illustrative units)',0,2000,300,50)
    st.caption('Not real healthcare costs. Review benefit is idealised; Tejas will replace the rule.')
visible=visible_weekly(weekly,clinic,replay_week)
if visible.empty: st.error('No clinic records for this replay week.');st.stop()
current=visible.iloc[-1]
positive_estimate=current.get('positive_cases_estimate')
if positive_estimate is None or str(positive_estimate)=='nan':
    st.info('No positive-case estimate available; decision slider calculation disabled.')
    decision=None
else:
    decision=demo_decision(float(current.estimated_sensitivity),float(positive_estimate),review_cost,missed_cost)
col1,col2,col3,col4=st.columns(4)
col1.metric('Estimated catch rate',f'{current.estimated_sensitivity:.1%}')
col2.metric('Uncertainty interval',f'{current.confidence_lower:.1%}–{current.confidence_upper:.1%}')
col3.metric('Scans this week',f'{int(current.total_scans):,}')
col4.metric('Recommended review', 'Yes' if decision and decision['recommended_action']=='review_recommended' else 'No' if decision else 'Unknown')
main,side=st.columns([2.2,1],gap='large')
with main:
    st.subheader('Estimated vs later-observed catch rate')
    st.plotly_chart(performance_chart(visible),use_container_width=True)
    st.caption('Expert observations appear only after their simulated label-arrival week. Intervals are synthetic placeholders until Tejas provides them.')
    with st.expander('Inspect records / export visible weeks'):
        st.dataframe(visible,use_container_width=True,hide_index=True)
        st.download_button('Download visible CSV',visible.to_csv(index=False),'clinicdrift_visible_weeks.csv','text/csv')
with side:
    st.subheader('Evidence → action')
    st.write(f'**Replay week:** {replay_week}')
    st.write(f'**Current monitoring status:** `{current.alarm_status}`')
    observed=visible[visible.observed_sensitivity.notna()]
    st.write(f'**Latest available expert-observed sensitivity:** {observed.iloc[-1].observed_sensitivity:.1%}' if len(observed) else '**Latest available expert-observed sensitivity:** Not yet available')
    st.write(f'**Expert-positive cases currently visible (latest labelled week):** {int(observed.iloc[-1].observed_positive_count)}' if len(observed) else '**Expert-positive cases:** Unavailable')
    if decision:
        st.metric('Hypothetical continuing loss',f"{decision['expected_continuation_cost']:,.0f} units")
        st.write(f"**Review cost:** {review_cost:,} units")
        st.info('**Recommend human review**' if decision['recommended_action']=='review_recommended' else '**Continue monitoring**')
        st.caption(decision['assumption'])
        payload=alert_json(current,decision,replay_week)
        st.download_button('Export alert JSON for Vansh',payload,'clinicdrift_alert.json','application/json')
    st.caption('No automatic withdrawal of a medical device. No causal claim about camera, country, or patients.')
st.divider()
st.subheader('Investigation timeline')
for _,r in visible.tail(5).iloc[::-1].iterrows():
    arrival='expert result available' if r.labels_available else f'expert grade pending until week {int(r.labels_available_week)}'
    st.write(f"**Week {int(r.clinic_week)}** · estimated {r.estimated_sensitivity:.1%} · {arrival}")
