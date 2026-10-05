"""Builds the receipt fonts in this folder (woff2 subsets, renamed).

Sources (Debian/Ubuntu packages): fonts-noto-core (Noto Sans Arabic, Noto Naskh Arabic — OFL-1.1),
fonts-liberation (Liberation Sans 2.1 — OFL-1.1, Reserved Font Name "Liberation") and
fonts-liberation-sans-narrow (Liberation Sans Narrow 1.07 — GPL-2 with font exception, see
LICENSE-LiberationSansNarrow.txt). The subsets are renamed "Hosny Receipt …" because both Liberation
licenses forbid the original name on a modified font.

Arabic files carry Arabic only (+ space / bidi controls), so digits and Latin fall through to the
Arial-metric Sans / Narrow files — the FERP slip prints its numbers in Arial and Arial Narrow.

    pip install fonttools brotli && python make_fonts.py
"""
import sys
from fontTools import subset
from fontTools.ttLib import TTFont

AR = "U+0020,U+00A0,U+0600-06FF,U+0750-077F,U+08A0-08FF,U+FB50-FDFF,U+FE70-FEFF,U+200B-200F,U+2010-2011,U+2028-202F,U+2066-2069,U+25CC"
LAT = "U+0020-007E,U+00A0-00FF,U+2010-2027,U+2030-205E,U+20AC,U+2116,U+2212,U+2066-2069,U+200E-200F"
SRC = {
    "ArabicCondensedLight": ("/usr/share/fonts/truetype/noto/NotoSansArabic-CondensedLight.ttf", AR),
    "ArabicCondensedMedium": ("/usr/share/fonts/truetype/noto/NotoSansArabic-CondensedMedium.ttf", AR),
    "ArabicSemiCondensedSemiBold": ("/usr/share/fonts/truetype/noto/NotoSansArabic-SemiCondensedSemiBold.ttf", AR),
    "ArabicSemiCondensedBold": ("/usr/share/fonts/truetype/noto/NotoSansArabic-SemiCondensedBold.ttf", AR),
    "ArabicSemiCondensedExtraBold": ("/usr/share/fonts/truetype/noto/NotoSansArabic-SemiCondensedExtraBold.ttf", AR),
    "NaskhSemiBold": ("/usr/share/fonts/truetype/noto/NotoNaskhArabic-SemiBold.ttf", AR),
    "Sans-Regular": ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", LAT),
    "Sans-Bold": ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", LAT),
    "SansNarrow-Regular": ("/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf", LAT),
    "SansNarrow-Bold": ("/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf", LAT),
}
names = sys.argv[1:] or list(SRC)
for name in names:
    src, uni = SRC[name]
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    opts.hinting = False
    opts.desubroutinize = True
    font = subset.load_font(src, opts)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=subset.parse_unicodes(uni))
    sub.subset(font)
    family = "Hosny Receipt " + name.replace("-", " ")
    for rec in font["name"].names:
        if rec.nameID in (1, 4, 16):
            rec.string = family
        elif rec.nameID == 6:
            rec.string = "HosnyReceipt-" + name
        elif rec.nameID == 3:
            rec.string = "HosnyReceipt-" + name + "-subset"
    out = f"HosnyReceipt-{name}.woff2"
    font.flavor = "woff2"
    font.save(out)
    print(out, TTFont(out).getBestCmap().__len__())
