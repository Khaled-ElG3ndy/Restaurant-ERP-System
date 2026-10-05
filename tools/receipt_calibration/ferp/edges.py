import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter
im = np.array(Image.open('ferp_photo.png').convert('L')).astype(float)
m = uniform_filter(im, 5); sq = uniform_filter(im*im, 5); std = np.sqrt(np.maximum(sq-m*m, 0))
H, W = im.shape
L, R = [], []
for y in range(80, 1250, 10):
    smooth = (std[y] < 6) & (m[y] > 120)
    # left edge: first x where smooth for next 8 px
    le = next((x for x in range(0, 200) if smooth[x:x+8].all()), None)
    re = next((x for x in range(W-1, 220, -1) if smooth[x-8:x].all()), None)
    L.append((y, le)); R.append((y, re))
for (y, l), (_, r) in zip(L, R):
    print(y, l, r, (r - l) if (l is not None and r is not None) else None)
