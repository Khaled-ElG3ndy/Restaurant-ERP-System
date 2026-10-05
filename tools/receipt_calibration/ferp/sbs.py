"""side by side: FERP (rectified, mapped to canvas coords) | ours (calib.png), cropped to a y-range."""
import sys
from PIL import Image, ImageDraw
X0, Y0, s = 10, -2.2, 576/586
rect = Image.open('rect.png').convert('L')
W = 576
H = int((rect.height - Y0) * s)
ferp = rect.transform((W, H), Image.AFFINE, (1/s, 0, X0, 0, 1/s, Y0), resample=Image.BICUBIC, fillcolor=128)
ours = Image.open(sys.argv[1]).convert('L')
y0, y1 = int(sys.argv[2]), int(sys.argv[3]); out = sys.argv[4]
mode = sys.argv[5] if len(sys.argv) > 5 else 'sbs'
if mode == 'sbs':
    im = Image.new('L', (W * 2 + 10, y1 - y0), 255)
    im.paste(ferp.crop((0, y0, W, y1)), (0, 0)); im.paste(ours.crop((0, y0, W, y1)), (W + 10, 0))
    im = im.convert('RGB')
else:  # overlay: FERP in red channel, ours in blue/green
    f = ferp.crop((0, y0, W, y1)); o = ours.crop((0, y0, W, y1))
    im = Image.merge('RGB', (f, o, o))
d = ImageDraw.Draw(im)
for y in range(((y0 // 50) + 1) * 50, y1, 50):
    d.text((2, y - y0), str(y), fill=(0, 120, 255))
im.save(out)
