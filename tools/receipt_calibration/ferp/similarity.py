import json, numpy as np, cv2
from PIL import Image
from skimage.metrics import structural_similarity as ssim
X0, Y0, s = 10, -2.2, 576/586
norm = Image.open('norm.png').convert('L')
W = 576; H = 2110
ferp = np.array(norm.transform((W, int((norm.height - Y0) * s)), Image.AFFINE, (1/s, 0, X0, 0, 1/s, Y0),
                               resample=Image.BICUBIC, fillcolor=255))[:H].astype(np.float32)
ours_raw = np.array(Image.open('/tmp/hosny-receipt-work/e2e/out/ferp_data_print_clipped.png').convert('L'))[:H].astype(np.float32)
# printed paper is a little fatter than the raster (dot gain); give ours the same softness as the photo
ours = cv2.GaussianBlur(ours_raw, (0, 0), 1.2)
F = ferp < 140
O = ours < 128
qr = np.zeros_like(F); qr[1820:2090, 150:410] = True
def f1(tol, mask_out=None):
    k = np.ones((2 * tol + 1, 2 * tol + 1), np.uint8)
    Fd = cv2.dilate(F.astype(np.uint8), k).astype(bool); Od = cv2.dilate(O.astype(np.uint8), k).astype(bool)
    keep = ~mask_out if mask_out is not None else np.ones_like(F)
    prec = (O & Fd & keep).sum() / max(1, (O & keep).sum())   # our ink that lands on FERP ink
    rec = (F & Od & keep).sum() / max(1, (F & keep).sum())     # FERP ink that we reproduce
    return prec, rec, 2 * prec * rec / (prec + rec)
for tol in (2, 4, 8):
    p, r, f = f1(tol, qr)
    print(f"ink overlap (QR excluded) tol {tol} dots ({tol*0.125:.2f} mm): ours-on-FERP {p:.1%}  FERP-reproduced {r:.1%}  F1 {f:.1%}")
p, r, f = f1(4)
print(f"ink overlap incl. QR, tol 4: F1 {f:.1%}")
# structural similarity on a 2x-downsampled, blurred pair (QR area blanked in both)
a = ferp.copy(); b = ours.copy(); a[qr] = 255; b[qr] = 255
a = cv2.resize(cv2.GaussianBlur(a, (0, 0), 1.5), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
b = cv2.resize(cv2.GaussianBlur(b, (0, 0), 1.5), (W // 2, H // 2), interpolation=cv2.INTER_AREA)
print(f"SSIM (QR excluded, 0.25 mm grid): {ssim(a, b, data_range=255):.3f}")
# element placement / size from the calibration measurements (bundle CSS)
T = json.load(open('ferp_canvas.json')); T.update(json.load(open('ferp_table.json')))
Fd = json.load(open('/tmp/hosny-receipt-work/calib/out/found.json'))
untrusted = {('v_printed', 2), ('v_printed', 3), ('phone', 2), ('phone', 3), ('r6_name', 3)}  # bent paper / ruled line
edges = []; sizes = []
for k, o in Fd.items():
    if k not in T: continue
    f = T[k]
    for i in range(4):
        if (k, i) not in untrusted:
            edges.append(abs(o[i] - f[i]))
    ow, fw = o[1] - o[0], (f[1] - f[0]) - 1.5
    sizes.append(abs(ow / fw - 1))
    if k not in ('v_printed', 'phone', 'r6_name'):
        oh, fh = o[3] - o[2], (f[3] - f[2]) - 1.5
        sizes.append(abs(oh / fh - 1))
edges = np.array(edges); sizes = np.array(sizes)
print(f"elements {len(Fd)}, edges {len(edges)}: mean {edges.mean():.1f} dots ({edges.mean()*0.125:.2f} mm); "
      f"within 0.5 mm {np.mean(edges <= 4):.1%}; within 1 mm {np.mean(edges <= 8):.1%}; max {edges.max():.0f} dots")
print(f"size (width/height) mean difference {sizes.mean():.1%}, median {np.median(sizes):.1%}")
# where is FERP ink we don't reproduce (1 mm tolerance)?
k = np.ones((17, 17), np.uint8)
Od = cv2.dilate(O.astype(np.uint8), k).astype(bool)
miss = F & ~Od & ~qr
ys, xs = np.nonzero(miss)
print("unmatched FERP ink px:", len(ys), "of", int((F & ~qr).sum()))
for name, (y0, y1) in {"logo": (0, 195), "header text": (195, 600), "meta": (600, 1030), "table": (1030, 1395),
                       "totals": (1395, 1620), "cashier/phone": (1620, 1800), "below": (1800, 2110)}.items():
    sel = (ys >= y0) & (ys < y1)
    tot = int((F[y0:y1] & ~qr[y0:y1]).sum())
    print(f"  {name:14s} unmatched {sel.sum():6d} / FERP ink {tot:6d}  ({sel.sum()/max(1,tot):.0%})  x-range {xs[sel].min() if sel.any() else '-'}-{xs[sel].max() if sel.any() else '-'}")
viz = np.full((H, W, 3), 255, np.uint8)
viz[F] = (230, 60, 60); viz[O] = (60, 90, 230); viz[F & O] = (0, 0, 0)
Image.fromarray(viz).save('overlay_diff.png')
print("---- content area (above the QR; the QR's modules depend on its data, and below it is the counter top)")
cut = np.zeros_like(F); cut[1800:] = True
for tol in (2, 4, 8):
    p, r, f = f1(tol, cut)
    print(f"tol {tol} dots ({tol*0.125:.2f} mm): ours-on-FERP {p:.1%}  FERP-reproduced {r:.1%}  F1 {f:.1%}")
a = ferp[:1800].copy(); b = ours[:1800].copy()
a = cv2.resize(cv2.GaussianBlur(a, (0, 0), 1.5), (W // 2, 900), interpolation=cv2.INTER_AREA)
b = cv2.resize(cv2.GaussianBlur(b, (0, 0), 1.5), (W // 2, 900), interpolation=cv2.INTER_AREA)
print(f"SSIM content area: {ssim(a, b, data_range=255):.3f}")
# QR: size & position only
qy, qx = np.nonzero(O[1800:2110]); fy, fx = np.nonzero(F[1830:2085, 140:420])
print("QR ours x", qx.min(), qx.max(), "y", qy.min()+1800, qy.max()+1800, "| FERP x", fx.min()+140, fx.max()+140, "y", fy.min()+1830, fy.max()+1830)
