"""Stacked, spatial and signature analysis (moved verbatim from the Streamlit app).

Nothing statistical was changed in the port: the 2 mm grid, the Gaussian
smoothing of defect counts and exposure *separately* (sigma = bandwidth / 2),
the coverage guard (``den > 1``), the global baseline, the exact binomial
recurrence tests with Benjamini-Hochberg q-values, the hotspot maximum-filter
peak detection (size 9, excess > 0.08, exposure >= max(4, 2 x wafers), top 8),
the radial zones and the 12 outer angular sectors are all as in the original.

Known characteristics deliberately left unchanged (flagged, not fixed):

* ``signature_indicators`` treats every *observed* spring as inspected and
  excludes uninspected springs from the zone totals (consistent with the
  "never counted as Good" rule).
* The BH q-values are exploratory: spatial and wafer-level observations are
  not independent (the original caption says so; the UI repeats it).
* When the global baseline is 0 or 1 (no contrast) every q is set to 1.0 and
  no p-values exist, exactly as before.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.stats import binomtest

STATES = ['Good','Low','Med','Killer','Uninspected']
SEVERITY = {'Low':1,'Med':2,'Killer':3}


def stacked_summary(ref: pd.DataFrame, data: pd.DataFrame, wafers: list[str]) -> pd.DataFrame:
    """Per-spring Inspected / Defects / Killer / Defect_Rate across ``wafers``.

    Rows follow the reference order (left merge). Springs with no observation
    have ``Inspected == 0`` and ``Defect_Rate`` NaN - missing, not zero.
    """
    # Missing observations remain missing, never assumed Good.
    sub=data[data.Wafer_ID.isin(wafers)].copy()
    sub['is_bad']=sub.Status.ne('Good').astype(int)
    agg=sub.groupby(['Die_Num','Spring_Num']).agg(Inspected=('is_bad','size'),Defects=('is_bad','sum'),Killer=('Status',lambda s:(s=='Killer').sum())).reset_index()
    out=ref.merge(agg,on=['Die_Num','Spring_Num'],how='left')
    out[['Inspected','Defects','Killer']]=out[['Inspected','Defects','Killer']].fillna(0).astype(int)
    out['Defect_Rate']=np.where(out.Inspected>0,out.Defects/out.Inspected,np.nan)
    return out


def spatial_analysis(stack: pd.DataFrame, data: pd.DataFrame, wafers: list[str], bandwidth: float = 5., min_coverage: float = .7):
    """Return ``(bins, rate, base, tests, peak_df)``.

    ``rate`` is indexed ``[x_bin, y_bin]`` (numpy ``histogram2d`` orientation);
    the Streamlit heatmap plotted ``rate.T``. ``tests`` carries ``p`` only when
    the baseline allows a binomial test, otherwise ``q`` is 1.0 throughout.
    """
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


def signature_indicators(stack: pd.DataFrame, data: pd.DataFrame, wafers: list[str]):
    """Return ``(zones, messages, sectors)``.

    ``zones`` and ``messages`` are exactly the original outputs. ``sectors``
    (the 12 outer-region angular sectors the heuristic evaluates) was computed
    but not displayed by the Streamlit app; it is returned as an extra so the
    UI can show what the angular test looked at. It does not alter anything.
    """
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
    overall=d.bad.mean()  # noqa: F841 - computed by the original, kept for parity
    edge=float(zones.loc['Edge (85-100)','Defect_Rate']) if 'Edge (85-100)' in zones.index else np.nan
    core=float(zones.loc['Core (0-35)','Defect_Rate']) if 'Core (0-35)' in zones.index else np.nan
    messages=[]
    if np.isfinite(edge) and np.isfinite(core) and edge>core*1.6 and edge-core>.05: messages.append('Edge/radial enrichment: outer wafer has elevated defect incidence.')
    if len(sectors) and sectors['size'].min()>10 and sectors['mean'].max()-sectors['mean'].min()>.12:messages.append('Angular nonuniformity: localized arc/sector concentration merits review.')
    if not messages:messages.append('No strong edge/sector indicator under current heuristic thresholds; inspect stack and hotspots.')
    messages.append('Spiral patterns require visual and model-based validation across multiple wafers; this utility does not assign a spiral label automatically.')
    return zones.reset_index(), messages, sectors.reset_index()


def header_metrics(ref: pd.DataFrame, selected_data: pd.DataFrame, selected: list[str]) -> dict:
    """The four header metrics (verbatim from the Streamlit page body)."""
    observations=len(selected_data);bad=int((selected_data.Status!='Good').sum())
    return {
        'wafers': len(selected),
        'springs_in_reference': int(len(ref)),
        'observations': int(observations),
        'bad': bad,
        'defect_rate': (bad/observations) if observations else None,
    }


def individual_wafer_status(ref: pd.DataFrame, selected_data: pd.DataFrame, wafer: str) -> tuple[pd.Series, pd.DataFrame]:
    """Per-reference-spring status for one wafer (missing -> ``Uninspected``) and the observed status counts.

    Verbatim from the "Individual wafer" tab: the status series follows the
    reference order; the counts table only counts *observed* springs, exactly
    like the original ``one.Status.value_counts()``.
    """
    one=selected_data[selected_data.Wafer_ID==wafer]
    merged=ref.merge(one[['Die_Num','Spring_Num','Status']],on=['Die_Num','Spring_Num'],how='left')
    counts=one.Status.value_counts().rename_axis('Status').reset_index(name='Count')
    return merged.Status.fillna('Uninspected'), counts
