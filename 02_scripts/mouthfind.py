import numpy as np
from PIL import Image
co=np.load("/home/claude/tanu/co.npy"); vcol=np.load("/home/claude/tanu/vcol.npy")
lum=vcol.mean(1)
reg=(co[:,1]<-0.33)&(co[:,2]>0.26)&(co[:,2]<0.395)&(np.abs(co[:,0])<0.22)
print("region",reg.sum())
for thr in [0.15,0.20,0.25,0.30,0.35]:
    d=reg&(lum<thr); print("thr",thr,"n",d.sum())
d=reg&(lum<0.28)
P=co[d]
print("n",len(P),"bbox",P.min(0),P.max(0))
# fit z = a + b x^2  (smile arc)
A=np.c_[np.ones(len(P)),P[:,0]**2]
coef,*_=np.linalg.lstsq(A,P[:,2],rcond=None)
print("smile fit: z = %.4f + %.4f*x^2"%tuple(coef))
res=P[:,2]-A@coef; print("residual std",res.std())
# corners: extreme x
xs=np.sort(P[:,0]); print("x p2,p98",np.percentile(P[:,0],2),np.percentile(P[:,0],98))
np.save("/home/claude/tanu/mouthpts.npy",P)
