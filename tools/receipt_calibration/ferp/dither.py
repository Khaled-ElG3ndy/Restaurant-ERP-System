"""Simulate pos EpsonPrinter.canvasToRaster (Floyd-Steinberg) on a canvas png."""
import sys, numpy as np
from PIL import Image
im = np.array(Image.open(sys.argv[1]).convert('RGB')).astype(float)
# Odoo: luminance = 0.299r+0.587g+0.114b ... threshold 127 with error diffusion
lum = im[..., 0] * 0.299 + im[..., 1] * 0.587 + im[..., 2] * 0.114
h, w = lum.shape
out = np.zeros_like(lum)
err = lum.copy()
for y in range(h):
    for x in range(w):
        old = min(255.0, max(0.0, err[y, x]))
        new = 0 if old < 128 else 255
        out[y, x] = new
        e = old - new
        if x + 1 < w: err[y, x + 1] += e * 7 / 16
        if y + 1 < h:
            if x > 0: err[y + 1, x - 1] += e * 3 / 16
            err[y + 1, x] += e * 5 / 16
            if x + 1 < w: err[y + 1, x + 1] += e * 1 / 16
Image.fromarray(out.astype(np.uint8)).save(sys.argv[2])
