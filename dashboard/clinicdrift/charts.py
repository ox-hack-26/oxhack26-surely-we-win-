"""Plotly figures for the ClinicDrift dashboard."""
import plotly.graph_objects as go

def performance_chart(df):
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=df.clinic_week,y=df.confidence_upper,mode='lines',line=dict(width=0),hoverinfo='skip',showlegend=False))
    fig.add_trace(go.Scatter(x=df.clinic_week,y=df.confidence_lower,mode='lines',fill='tonexty',fillcolor='rgba(48,134,183,.18)',line=dict(width=0),name='Estimate uncertainty',hoverinfo='skip'))
    fig.add_trace(go.Scatter(x=df.clinic_week,y=df.estimated_sensitivity,mode='lines+markers',name='Estimated catch rate',line=dict(color='#267eae',width=3)))
    fig.add_trace(go.Scatter(x=df.clinic_week,y=df.observed_sensitivity,mode='markers+lines',name='Observed after expert labels',line=dict(color='#e39b45',width=2,dash='dot')))
    fig.update_layout(height=400,margin=dict(l=10,r=10,t=20,b=10),yaxis=dict(range=[0,1],tickformat='.0%',title='Sensitivity'),xaxis=dict(title='Simulated clinic-week',dtick=1),legend=dict(orientation='h',y=-.24),hovermode='x unified')
    return fig
