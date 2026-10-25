import plotly.graph_objects as go

from ui.theme import ALARM, BELIEF, BELIEF_BAND, DRIFT, ESTIMATE, GRADES, MUTED

def catch_chart(df, show_hindsight=False):
    fig = go.Figure()
    x=df['week']
    fig.add_trace(go.Scatter(x=x,y=df['catch_high'],mode='lines',line=dict(width=0),showlegend=False,hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=x,y=df['catch_low'],mode='lines',fill='tonexty',fillcolor=BELIEF_BAND,line=dict(width=0),name='90% uncertainty band',hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=x,y=df['catch_rate'],name='ClinicDrift belief',mode='lines+markers',line=dict(color=BELIEF,width=2.5)))
    fig.add_trace(go.Scatter(x=x,y=df['est_sensitivity'],name='Naive image-only estimate',mode='lines',line=dict(color=ESTIMATE,dash='dash',width=2)))
    if show_hindsight and 'true_sensitivity' in df:
        replay_week = int(df['week'].max())
        graded = df[df['week'] <= replay_week - 7]
        if not graded.empty:
            fig.add_trace(go.Scatter(
                x=graded['week'],
                y=graded['true_sensitivity'],
                name='Real (known later)',
                mode='lines+markers',
                line=dict(color=GRADES, dash='dot', width=2)
            ))
    fig.update_layout(height=370,margin=dict(l=5,r=5,t=20,b=10),yaxis=dict(title='Catch rate',range=[0,1],tickformat='.0%'),xaxis=dict(title='Simulated week',dtick=1),hovermode='x unified',legend=dict(orientation='h',y=-.3))
    return fig

def drift_chart(df):
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=df.week,y=df.drift_auc,mode='lines+markers',name='Drift AUC',line=dict(color=DRIFT,width=2.5)))
    fig.add_hline(y=.7,line_dash='dot',line_color=MUTED,annotation_text='Trust begins falling (0.7)',annotation_font_color=MUTED)
    fig.add_hline(y=.9,line_dash='dash',line_color=ALARM,annotation_text='Untrusted (0.9)',annotation_font_color=MUTED)
    fig.update_layout(height=280,margin=dict(l=5,r=5,t=15,b=5),yaxis=dict(range=[.45,1.02],title='Drift AUC'),xaxis=dict(title='Simulated week',dtick=1))
    return fig
