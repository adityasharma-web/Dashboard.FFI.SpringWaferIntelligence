"""Sentient spring wafer inspection / stacked wafer spatial analysis."""
from pathlib import Path
import io
import re
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent
REF_DIR = ROOT / 'coordinates'
COLORS = {'Good':'#21a653','Low':'#f4d43b','Med':'#f38a24','Killer':'#df3537','Uninspected':'#aab4c2'}
STATES = ['Good','Low','Med','Killer','Uninspected']
SEVERITY = {'Low':1,'Med':2,'Killer':3}
st.set_page_config(page_title='Sentient | Spring Wafer Intelligence', layout='wide')
st.title('Spring Wafer Intelligence')
st.caption('Product-based coordinate registration | Individual inspection | Multi-wafer spatial signatures')

@st.cache_data(show_spinner=False)
def load_reference(product):
    matches = [p for p in REF_DIR.iterdir() if p.suffix.lower() in ('.xlsx','.csv') and (p.stem == product or p.stem.startswith(product + ' '))]
    if not matches: raise ValueError(f'No reference found for {product} in coordinates/')
    p = sorted(matches, key=lambda x: x.suffix != '.xlsx')[0]
    df = pd.read_excel(p) if p.suffix.lower()=='.xlsx' else pd.read_csv(p)
    df.columns = [re.sub(r'\s*\(.*?\)','',str(c)).strip() for c in df.columns]
    rename = {'Die_Num':'Die_Num','Spring_Num':'Spring_Num','X':'X','Y':'Y','X_Source_mm':'X','Y_Source_mm':'Y'}
    df = df.rename(columns=rename)
    required = {'Die_Num','Spring_Num','X','Y'}
    if not required.issubset(df.columns): raise ValueError(f'Reference must contain {required}. Found: {df.columns.tolist()}')
    df = df[['Die_Num','Spring_Num','X','Y']].copy()
    for c in df.columns: df[c]=pd.to_numeric(df[c],errors='raise')
    if df[['Die_Num','Spring_Num']].duplicated().any(): raise ValueError('Duplicate spring keys in reference')
    df[['Die_Num','Spring_Num']]=df[['Die_Num','Spring_Num']].astype(int)
    cx=(df.X.min()+df.X.max())/2;cy=(df.Y.min()+df.Y.max())/2
    df['x']=df.X-cx;df['y']=df.Y-cy
    return df, (cx,cy)

def read_inspection(file, product, valid_keys):
    raw = pd.read_excel(file) if file.name.lower().endswith('.xlsx') else pd.read_csv(file)
    raw.columns=[str(c).strip() for c in raw.columns]
    req={'Product','Die_Num','Spring_Num','Defect','Defect_Severity'}
    if not req.issubset(raw.columns): raise ValueError(f'{file.name}: missing {sorted(req-set(raw.columns))}')
    raw['Product']=raw.Product.astype(str).str.strip()
    if not raw.Product.eq(product).all(): raise ValueError(f'{file.name}: product mismatch; expected {product}')
    for c in ('Die_Num','Spring_Num'):
        raw[c]=pd.to_numeric(raw[c],errors='raise')
        if raw[c].isna().any() or not (raw[c]%1==0).all():raise ValueError(f'{file.name}: invalid {c}')
        raw[c]=raw[c].astype(int)
    raw['Defect']=raw.Defect.astype(str).str.strip().str.upper()
    if not raw.Defect.isin(['Y','N']).all():raise ValueError(f'{file.name}: Defect must be Y or N')
    raw['Defect_Severity']=raw.Defect_Severity.fillna('').astype(str).str.strip().str.lower().map({'low':'Low','med':'Med','medium':'Med','killer':'Killer','':'','nan':''})
    bad=raw.Defect.eq('Y')
    if raw.loc[bad,'Defect_Severity'].isna().any() or raw.loc[bad,'Defect_Severity'].eq('').any():
        raise ValueError(f'{file.name}: Y defects require Low, Med, or Killer severity')
    if raw[['Die_Num','Spring_Num']].duplicated().any():raise ValueError(f'{file.name}: duplicate Die_Num/Spring_Num')
    keys=pd.MultiIndex.from_frame(raw[['Die_Num','Spring_Num']])
    if not keys.isin(valid_keys).all():raise ValueError(f'{file.name}: inspection contains unknown spring keys')
    raw['Status']=np.where(bad,raw.Defect_Severity,'Good')
    raw['Wafer_ID']=raw['Wafer_ID'].astype(str).str.strip() if 'Wafer_ID' in raw.columns else Path(file.name).stem
    if raw.Wafer_ID.nunique()!=1:raise ValueError(f'{file.name}: one Wafer_ID per file required')
    return raw[['Wafer_ID','Die_Num','Spring_Num','Status']]

def decorate(fig, ref, title, die_labels=True):
    theta=np.linspace(0,2*np.pi,361)
    fig.add_trace(go.Scatter(x=100*np.cos(theta),y=100*np.sin(theta),mode='lines',line=dict(color='#26394f',width=2),hoverinfo='skip',showlegend=False))
    fig.add_trace(go.Scatter(x=[-3,0,3],y=[-99.955,-97.2,-99.955],mode='lines',fill='toself',fillcolor='white',line=dict(color='#26394f',width=1.5),hoverinfo='skip',showlegend=False))
    if die_labels:
        bounds=ref.groupby('Die_Num').agg(xmin=('x','min'),xmax=('x','max'),ymin=('y','min'),ymax=('y','max'))
        for die,b in bounds.iterrows():
            fig.add_shape(type='rect',x0=b.xmin-2,y0=b.ymin-.2,x1=b.xmax+2,y1=b.ymax+.2,line=dict(color='rgba(110,125,140,.55)',width=.7))
            fig.add_annotation(x=(b.xmin+b.xmax)/2,y=b.ymax+1.3,text=str(die),showarrow=False,font=dict(size=8,color='#52647a'))
    fig.update_layout(title=title,template='plotly_white',height=780,margin=dict(l=25,r=20,t=65,b=25),legend=dict(orientation='h',y=1.06),hovermode='closest')
    fig.update_xaxes(range=[-106,106],title='X (mm)')
    fig.update_yaxes(range=[-108,106],title='Y (mm)',scaleanchor='x',scaleratio=1)
    return fig

def springs_plot(ref, values, title, categorical=True, labels=True):
    fig=go.Figure()
    if categorical:
        for state in STATES:
            idx=np.flatnonzero(values.to_numpy()==state)
            if not len(idx):continue
            a=ref.iloc[idx]; x=a.x.to_numpy();y=a.y.to_numpy()
            # Horizontal segments are exactly 4 mm wide in the same coordinate space as the wafer.
            xs=np.column_stack((x-2,x+2,np.full(len(x),np.nan))).ravel()
            ys=np.column_stack((y,y,np.full(len(y),np.nan))).ravel()
            fig.add_trace(go.Scattergl(x=xs,y=ys,mode='lines',line=dict(color=COLORS[state],width=2),name=state,hoverinfo='skip'))
        # Hover layer: individual physical spring locations, all coordinate keyed.
        fig.add_trace(go.Scattergl(x=ref.x,y=ref.y,mode='markers',marker=dict(size=5,opacity=.015,color='#111111'),customdata=np.column_stack([ref.Die_Num,ref.Spring_Num,values]),hovertemplate='Die %{customdata[0]} | Spring %{customdata[1]}<br>Status: %{customdata[2]}<extra></extra>',showlegend=False))
    else:
        v=values.to_numpy(dtype=float)
        fig.add_trace(go.Scattergl(x=ref.x,y=ref.y,mode='markers',marker=dict(size=5,color=v,colorscale='YlOrRd',cmin=0,cmax=1,colorbar=dict(title='Defect frequency')),customdata=np.column_stack([ref.Die_Num,ref.Spring_Num,values]),hovertemplate='Die %{customdata[0]} | Spring %{customdata[1]}<br>Defect rate %{customdata[2]:.1%}<extra></extra>',name='Observed frequency'))
    return decorate(fig,ref,title,labels)

def stacked_summary(ref, data, wafers):
    # Missing observations remain missing, never assumed Good.
    sub=data[data.Wafer_ID.isin(wafers)].copy()
    sub['is_bad']=sub.Status.ne('Good').astype(int)
    agg=sub.groupby(['Die_Num','Spring_Num']).agg(Inspected=('is_bad','size'),Defects=('is_bad','sum'),Killer=('Status',lambda s:(s=='Killer').sum())).reset_index()
    out=ref.merge(agg,on=['Die_Num','Spring_Num'],how='left')
    out[['Inspected','Defects','Killer']]=out[['Inspected','Defects','Killer']].fillna(0).astype(int)
    out['Defect_Rate']=np.where(out.Inspected>0,out.Defects/out.Inspected,np.nan)
    return out

def spatial_analysis(stack, data, wafers, bandwidth=5., min_coverage=.7):
    # 2 mm grid; spatial kernel smooths defect counts and inspected counts separately.
    bins=np.arange(-102,104,2.)
    valid=stack.Inspected>0
    sub=stack[valid]
    defect,xe,ye=np.histogram2d(sub.x,sub.y,bins=[bins,bins],weights=sub.Defects)
    exposure,_,_=np.histogram2d(sub.x,sub.y,bins=[bins,bins],weights=sub.Inspected)
    sig=bandwidth/2.
    num=gaussian_filter(defect,sig,mode='constant');den=gaussian_filter(exposure,sig,mode='constant')
    rate=np.divide(num,den,out=np.full_like(num,np.nan),where=den>1)
    base=float(sub.Defects.sum()/sub.Inspected.sum()) if sub.Inspected.sum() else 0.
    # Binomial recurrence at exact spring positions; BH correction, exploratory (spatial dependence).
    tests=sub[sub.Inspected>=max(2,int(np.ceil(min_coverage*len(wafers))))].copy()
    if base>0 and base<1 and len(tests):
        tests['p']= [binomtest(int(k),int(n),base,alternative='greater').pvalue for k,n in zip(tests.Defects,tests.Inspected)]
        order=np.argsort(tests.p.to_numpy());p=tests.p.to_numpy()[order];m=len(p)
        q=np.minimum.accumulate((p*m/np.arange(1,m+1))[::-1])[::-1]
        arr=np.empty(m);arr[order]=np.minimum(q,1);tests['q']=arr
    else:tests['q']=1.
    # Peak candidates are spatial excess maxima, not confirmed root causes.
    excess=rate-base
    mask=np.isfinite(excess)&(den>=max(4,len(wafers)*2))
    score=np.where(mask,excess,-np.inf)
    peaks=np.argwhere((score==maximum_filter(score,size=9)) & (score>0.08))
    peaks=sorted(peaks,key=lambda ij:score[tuple(ij)],reverse=True)[:8]
    peak_df=pd.DataFrame([{'X_mm':round(float((bins[i]+bins[i+1])/2),1),'Y_mm':round(float((bins[j]+bins[j+1])/2),1),'Local_defect_rate':round(float(rate[i,j]),3),'Excess_vs_global':round(float(excess[i,j]),3)} for i,j in peaks])
    return bins,rate,base,tests,peak_df

def signature_indicators(stack, data, wafers):
    # Descriptive indicators; never automatically assign a process cause.
    d=data[data.Wafer_ID.isin(wafers)].merge(stack[['Die_Num','Spring_Num','x','y']],on=['Die_Num','Spring_Num'])
    d['bad']=d.Status.ne('Good')
    d['radius']=np.hypot(d.x,d.y)
    d['zone']=pd.cut(d.radius,[-1,35,65,85,101],labels=['Core (0-35)','Mid (35-65)','Outer (65-85)','Edge (85-100)'])
    zones=d.groupby('zone',observed=False).agg(Inspected=('bad','size'),Defects=('bad','sum'))
    zones['Defect_Rate']=zones.Defects/zones.Inspected.clip(lower=1)
    # Angular nonuniformity in the outer region can indicate a directional/arc-like signature.
    outer=d[d.radius>=65].copy()
    outer['sector']=pd.cut(np.mod(np.arctan2(outer.y,outer.x),2*np.pi),bins=np.linspace(0,2*np.pi,13),include_lowest=True)
    sectors=outer.groupby('sector',observed=False).bad.agg(['mean','size'])
    overall=d.bad.mean()
    edge=float(zones.loc['Edge (85-100)','Defect_Rate']) if 'Edge (85-100)' in zones.index else np.nan
    core=float(zones.loc['Core (0-35)','Defect_Rate']) if 'Core (0-35)' in zones.index else np.nan
    messages=[]
    if np.isfinite(edge) and np.isfinite(core) and edge>core*1.6 and edge-core>.05: messages.append('Edge/radial enrichment: outer wafer has elevated defect incidence.')
    if len(sectors) and sectors['size'].min()>10 and sectors['mean'].max()-sectors['mean'].min()>.12:messages.append('Angular nonuniformity: localized arc/sector concentration merits review.')
    if not messages:messages.append('No strong edge/sector indicator under current heuristic thresholds; inspect stack and hotspots.')
    messages.append('Spiral patterns require visual and model-based validation across multiple wafers; this utility does not assign a spiral label automatically.')
    return zones.reset_index(), messages

st.sidebar.header('1 · Product & inputs')
products=sorted({re.split(r' ',p.stem)[0] for p in REF_DIR.iterdir() if p.suffix.lower() in ('.xlsx','.csv')})
product=st.sidebar.selectbox('Product',products) if products else st.sidebar.text_input('Product ID','152-900530D')
files=st.sidebar.file_uploader('Inspection files (CSV/XLSX; one wafer per file)',type=['csv','xlsx'],accept_multiple_files=True)
show_labels=st.sidebar.checkbox('Show gang outlines and labels',value=True)
bandwidth=st.sidebar.slider('Spatial smoothing bandwidth (mm)',2.,15.,5.,1.)
try:ref,center=load_reference(product)
except Exception as e:st.error(str(e));st.stop()
valid_keys=pd.MultiIndex.from_frame(ref[['Die_Num','Spring_Num']])
st.sidebar.caption(f'Coordinate center inferred from extents: X={center[0]:.3f}, Y={center[1]:.3f} mm. Notch down assumed.')
if not files:
    st.info('Upload one or more inspection files to begin. A sample multi-wafer dataset is included in examples/.')
    st.dataframe(ref[['Die_Num','Spring_Num','X','Y']].head(10),hide_index=True)
    st.stop()
frames=[];errors=[]
for f in files:
    try:frames.append(read_inspection(f,product,valid_keys))
    except Exception as e:errors.append(str(e))
if errors:
    for e in errors:st.error(e)
    st.stop()
data=pd.concat(frames,ignore_index=True)
if data[['Wafer_ID','Die_Num','Spring_Num']].duplicated().any():st.error('Duplicate wafer/spring keys across input files. Ensure unique Wafer_ID per file.');st.stop()
wafers=sorted(data.Wafer_ID.unique())
selected=st.sidebar.multiselect('Wafers to analyze',wafers,default=wafers)
if not selected:st.warning('Select at least one wafer.');st.stop()
selected_data=data[data.Wafer_ID.isin(selected)]
stack=stacked_summary(ref,selected_data,selected)
observations=len(selected_data);bad=(selected_data.Status!='Good').sum()
c1,c2,c3,c4=st.columns(4)
c1.metric('Wafers',len(selected));c2.metric('Springs in reference',f'{len(ref):,}');c3.metric('Inspected observations',f'{observations:,}');c4.metric('Defect rate',f'{bad/observations:.1%}' if observations else 'N/A')
individual,stacktab,patterns,gangs,export=st.tabs(['Individual wafer','Stacked wafer','Spatial signatures','Gang yield','Export'])
with individual:
    wafer=st.selectbox('Wafer ID',selected,key='individual')
    one=selected_data[selected_data.Wafer_ID==wafer]
    merged=ref.merge(one[['Die_Num','Spring_Num','Status']],on=['Die_Num','Spring_Num'],how='left')
    st.plotly_chart(springs_plot(ref,merged.Status.fillna('Uninspected'),f'{product} · {wafer}',labels=show_labels),use_container_width=True)
    st.caption('Green = Good | Yellow = Low | Orange = Med | Red = Killer | Gray = uninspected. Horizontal spring segments span 4 mm in X; visual line thickness is screen-dependent.')
    st.dataframe(one.Status.value_counts().rename_axis('Status').reset_index(name='Count'),hide_index=True)
with stacktab:
    st.plotly_chart(springs_plot(ref,stack.Defect_Rate.fillna(0),f'{product} · {len(selected)} wafer stack · defect incidence',categorical=False,labels=show_labels),use_container_width=True)
    st.caption('Color indicates observed defects / inspected observations per spring. Springs never inspected are displayed at zero for map rendering only; use the table below to distinguish missing coverage.')
    st.dataframe(stack[['Die_Num','Spring_Num','Inspected','Defects','Killer','Defect_Rate']],hide_index=True,height=300)
with patterns:
    bins,rate,baseline,tests,peaks=spatial_analysis(stack,selected_data,selected,bandwidth)
    fig=go.Figure(go.Heatmap(x=(bins[:-1]+bins[1:])/2,y=(bins[:-1]+bins[1:])/2,z=rate.T,zmin=0,zmax=1,colorscale='YlOrRd',colorbar=dict(title='Local defect rate'),hoverongaps=False))
    decorate(fig,ref,f'Smoothed stacked defect incidence · {bandwidth:.0f} mm bandwidth',die_labels=False)
    st.plotly_chart(fig,use_container_width=True)
    st.caption('Gaussian-smoothed defect counts divided by Gaussian-smoothed inspection exposure. Blank areas have insufficient coverage. Patterns are exploratory; adjacent pixels are statistically dependent.')
    zones,messages=signature_indicators(stack,selected_data,selected)
    st.subheader('Signature indicators')
    for msg in messages:st.write('• '+msg)
    st.dataframe(zones,hide_index=True)
    st.subheader('Candidate recurring hotspots')
    st.dataframe(peaks if len(peaks) else pd.DataFrame({'Result':['No peaks exceed current excess threshold']}),hide_index=True)
    st.subheader('Spring-level recurrence')
    st.caption(f'Global baseline = {baseline:.1%}. Exact binomial enrichment tests with Benjamini-Hochberg exploratory q-values; interpret cautiously because spatial and wafer-level observations may not be independent.')
    st.dataframe(tests.sort_values(['q','Defects'],ascending=[True,False])[['Die_Num','Spring_Num','Inspected','Defects','q']].head(100),hide_index=True)
with gangs:
    g=selected_data.assign(Bad=lambda d:d.Status.ne('Good')).groupby(['Wafer_ID','Die_Num']).agg(Inspected=('Bad','size'),Bad=('Bad','sum')).reset_index()
    expected=ref.groupby('Die_Num').size().rename('Total_Springs').reset_index()
    g=g.merge(expected,on='Die_Num');g['Bad_Pct']=g.Bad/g.Total_Springs
    g['Complete_Inspection']=g.Inspected.eq(g.Total_Springs)
    g['Disposition']=np.select([g.Bad_Pct>.60,~g.Complete_Inspection],['SCRAP','INCOMPLETE'],default='PASS')
    st.caption('Scrap when bad springs / total springs in gang > 60%. Incomplete inspections are flagged; observed bad counts can already establish scrap.')
    st.dataframe(g.sort_values(['Wafer_ID','Die_Num']),hide_index=True,height=450)
    st.metric('Scrapped wafer-gangs',int((g.Disposition=='SCRAP').sum()))
with export:
    st.download_button('Download stacked spring metrics (CSV)',stack[['Die_Num','Spring_Num','x','y','Inspected','Defects','Killer','Defect_Rate']].to_csv(index=False).encode(),file_name=f'{product}_stacked_spring_metrics.csv',mime='text/csv')
    st.download_button('Download normalized inspection data (CSV)',selected_data.to_csv(index=False).encode(),file_name=f'{product}_inspection_normalized.csv',mime='text/csv')
    st.caption('Coordinates are product-referenced; severity and defect observations are inspection-file values, never synthesized by the application.')
