import numpy as np, cv2, json
norm = cv2.imread('norm.png', cv2.IMREAD_GRAYSCALE)
X = [10, 131, 231.5, 329, 410.5, 595.5]   # left .. right borders (rect)
Yr = [1051, 1117, 1171, 1216, 1269, 1312, 1364, 1409]  # row lines, right part
cols = ['total', 'tax', 'unit', 'qty', 'name']   # left -> right
X0, Y0, s = 10, -2.2, 576/586
out = {}
for r in range(len(Yr) - 1):
    for c in range(5):
        x0, x1 = int(X[c] + 4), int(X[c+1] - 4)
        y0, y1 = int(Yr[r] + 5), int(Yr[r+1] - 4)
        # left columns sit a few px lower (residual tilt): widen the window downward
        if c < 2: y0 += 2; y1 += 3
        sub = norm[y0:y1, x0:x1] < (115 if r == 0 else 140)
        sub = cv2.morphologyEx(sub.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2,2),np.uint8)).astype(bool)
        ys, xs = np.nonzero(sub)
        if not len(ys): continue
        b = [x0+xs.min(), x0+xs.max(), y0+ys.min(), y0+ys.max()]
        k = f"{'th' if r == 0 else 'r'+str(r)}_{cols[c]}"
        out[k] = [round((b[0]-X0)*s,1), round((b[1]-X0)*s,1), round((b[2]-Y0)*s,1), round((b[3]-Y0)*s,1)]
        v = out[k]
        print(f"{k:9s} x {v[0]:6.1f}-{v[1]:6.1f} y {v[2]:7.1f}-{v[3]:7.1f} w {v[1]-v[0]:5.1f} h {v[3]-v[2]:5.1f} cx {(v[0]+v[1])/2:6.1f} cy {(v[2]+v[3])/2:7.1f}")
json.dump(out, open('ferp_table.json', 'w'))
