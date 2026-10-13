"""Gang (die) disposition, extracted verbatim from the Streamlit "Gang yield" tab.

Rule (unchanged): ``Bad_Pct = Bad / Total_Springs`` where ``Total_Springs`` is
the number of springs the *reference* lists for the gang (not the number
inspected). ``SCRAP`` when ``Bad_Pct > 0.60`` (strictly greater; exactly 60 %
is not scrap), otherwise ``INCOMPLETE`` when fewer springs were inspected than
the reference lists, otherwise ``PASS``. Because the scrap test is evaluated
first, observed bad counts can establish scrap even for an incomplete
inspection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SCRAP_THRESHOLD = .60
GANG_YIELD_RULE = 'Scrap when bad springs / total springs in gang > 60%. Incomplete inspections are flagged; observed bad counts can already establish scrap.'


def gang_yield(ref: pd.DataFrame, selected_data: pd.DataFrame) -> pd.DataFrame:
    """Per-wafer per-gang table: Wafer_ID, Die_Num, Inspected, Bad, Total_Springs, Bad_Pct, Complete_Inspection, Disposition."""
    g=selected_data.assign(Bad=lambda d:d.Status.ne('Good')).groupby(['Wafer_ID','Die_Num']).agg(Inspected=('Bad','size'),Bad=('Bad','sum')).reset_index()
    expected=ref.groupby('Die_Num').size().rename('Total_Springs').reset_index()
    g=g.merge(expected,on='Die_Num');g['Bad_Pct']=g.Bad/g.Total_Springs
    g['Complete_Inspection']=g.Inspected.eq(g.Total_Springs)
    g['Disposition']=np.select([g.Bad_Pct>SCRAP_THRESHOLD,~g.Complete_Inspection],['SCRAP','INCOMPLETE'],default='PASS')
    return g.sort_values(['Wafer_ID','Die_Num']).reset_index(drop=True)
