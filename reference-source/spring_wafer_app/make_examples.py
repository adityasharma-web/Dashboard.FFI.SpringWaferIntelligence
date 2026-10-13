"""Generate reproducible, synthetic demonstration inspection files."""
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parent
ref=pd.read_excel(ROOT/'coordinates'/'152-900530D.xlsx')
ref.columns=['Die_Num','Spring_Num','feature','X','Y']
x=ref.X.to_numpy();y=ref.Y.to_numpy()
x=x-(x.min()+x.max())/2;y=y-(y.min()+y.max())/2
r=np.hypot(x,y);theta=np.arctan2(y,x)
for i in range(1,7):
    rng=np.random.default_rng(20261009+i)
    spiral=np.exp(-.5*(np.angle(np.exp(1j*(theta-(r/14.+.15))))/.32)**2)
    ring=np.exp(-.5*((r-75)/8)**2)
    spot=np.exp(-.5*(((x-48)/11)**2+((y+32)/13)**2))
    p=np.clip(.025+.31*spiral+.17*ring+.24*spot+.07*(r>87)+rng.normal(0,.012,len(r)),.001,.9)
    defective=rng.random(len(r))<p
    sev=rng.choice(['Low','Med','Killer'],len(r),p=[.50,.35,.15])
    out=pd.DataFrame({'Product':'152-900530D','Wafer_ID':f'SYNTH_WAFER_{i:02d}','Die_Num':ref.Die_Num,'Spring_Num':ref.Spring_Num,'Defect':np.where(defective,'Y','N'),'Defect_Severity':np.where(defective,sev,'')})
    out.to_csv(ROOT/'examples'/f'SYNTH_WAFER_{i:02d}.csv',index=False)
    print(i,round(defective.mean(),4))
