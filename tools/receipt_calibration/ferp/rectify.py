import numpy as np, cv2
im = cv2.imread('ferp_photo.png')
# paper edge lines fitted from edges.py (x as function of y)
ys = np.arange(260, 1230, 10)
import subprocess
rows = [l.split() for l in subprocess.run(['./qrenv/bin/python','edges.py'],capture_output=True,text=True).stdout.splitlines()]
d = {int(r[0]):(int(r[1]),int(r[2])) for r in rows if r[1]!='None' and r[2]!='None'}
Y = np.array([y for y in d if 260<=y<=1220]); Lx = np.array([d[y][0] for y in Y]); Rx = np.array([d[y][1] for y in Y])
lp = np.polyfit(Y, Lx, 1); rp = np.polyfit(Y, Rx, 1)
print('left', lp, 'right', rp)
theta = np.arctan((lp[0]+rp[0])/2)  # paper rotation
sl = -np.tan(theta)  # slope of paper-horizontal lines dy/dx
def inter(edge, x0, y0):
    # line through (x0,y0) with slope sl: y = y0 + sl*(x-x0); edge: x = a*y+b
    a,b = edge
    # x = a*(y0 + sl*(x-x0)) + b -> x(1 - a*sl) = a*y0 - a*sl*x0 + b
    x = (a*y0 - a*sl*x0 + b)/(1-a*sl); y = y0 + sl*(x-x0); return (x,y)
A = (200, 300); B = (200, 1200)
TL = inter(lp, *A); TR = inter(rp, *A); BL = inter(lp, *B); BR = inter(rp, *B)
wA = np.hypot(TR[0]-TL[0], TR[1]-TL[1]); wB = np.hypot(BR[0]-BL[0], BR[1]-BL[1])
dist = np.hypot((BL[0]+BR[0])/2-(TL[0]+TR[0])/2, (BL[1]+BR[1])/2-(TL[1]+TR[1])/2)
# vertical dots: integrate 640/width linearly varying
wavg = (wA - wB)/np.log(wA/wB) if abs(wA-wB)>1e-6 else wA
Ldots = dist*640/wavg
print('widths', wA, wB, 'dist', dist, 'Ldots', Ldots)
src = np.float32([TL, TR, BL, BR])
# paper coords: x 0..640 ; y: line A at 300*? -> keep offset so the logo top is visible: map A to y=A_dots
yA = 400.0
dst = np.float32([[0,yA],[640,yA],[0,yA+Ldots],[640,yA+Ldots]])
Hm = cv2.getPerspectiveTransform(src, dst)
np.save('H.npy', Hm)
out = cv2.warpPerspective(im, Hm, (640, int(yA+Ldots+250)), flags=cv2.INTER_CUBIC, borderValue=(80,80,80))
cv2.imwrite('rect.png', out)
print(out.shape)
