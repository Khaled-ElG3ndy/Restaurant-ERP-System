"""Generate static/src/css/ferp_receipt.css from a measured spec (all numbers = canvas px = printer dots).

The FERP slip was rectified and scaled so its table spans the full 576-dot print width (72 mm on the
branch TM-T20III); every number below comes from calibrate.py comparing ink in the real POS print
canvas against the FERP ink boxes.
"""
import json, os, copy

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_FILE = os.path.join(HERE, "spec.json")

FONTS = {
    # family name -> [(file, weight)]; the Arabic files answer every weight (no faux bold), so a
    # bold run still takes its digits from the bold Sans file.
    "Hosny Receipt Arabic Light": [("HosnyReceipt-ArabicCondensedLight.woff2", "100 900")],
    "Hosny Receipt Arabic Medium": [("HosnyReceipt-ArabicCondensedMedium.woff2", "100 900")],
    "Hosny Receipt Arabic SemiBold": [("HosnyReceipt-ArabicSemiCondensedSemiBold.woff2", "100 900")],
    "Hosny Receipt Arabic Bold": [("HosnyReceipt-ArabicSemiCondensedBold.woff2", "100 900")],
    "Hosny Receipt Arabic Heavy": [("HosnyReceipt-ArabicSemiCondensedExtraBold.woff2", "100 900")],
    "Hosny Receipt Naskh": [("HosnyReceipt-NaskhSemiBold.woff2", "100 900")],
    "Hosny Receipt Sans": [("HosnyReceipt-Sans-Regular.woff2", 400), ("HosnyReceipt-Sans-Bold.woff2", 700)],
    "Hosny Receipt Narrow": [("HosnyReceipt-SansNarrow-Regular.woff2", 400), ("HosnyReceipt-SansNarrow-Bold.woff2", 700)],
}

# font key -> css font-family stack + weight
FACE = {
    "ar-light": ('"Hosny Receipt Arabic Light", "Hosny Receipt Sans"', 400),
    "ar-medium": ('"Hosny Receipt Arabic Medium", "Hosny Receipt Sans"', 400),
    "ar-semibold": ('"Hosny Receipt Arabic SemiBold", "Hosny Receipt Sans"', 700),
    "ar-bold": ('"Hosny Receipt Arabic Bold", "Hosny Receipt Sans"', 700),
    "ar-heavy": ('"Hosny Receipt Arabic Heavy", "Hosny Receipt Sans"', 700),
    "naskh": ('"Hosny Receipt Naskh", "Hosny Receipt Sans"', 700),
    "sans": ('"Hosny Receipt Sans", "Hosny Receipt Arabic Medium"', 400),
    "sans-bold": ('"Hosny Receipt Sans", "Hosny Receipt Arabic Bold"', 700),
    "narrow": ('"Hosny Receipt Narrow", "Hosny Receipt Arabic Medium"', 400),
    "narrow-bold": ('"Hosny Receipt Narrow", "Hosny Receipt Arabic Bold"', 700),
}

DEFAULT = {
    "width": 576,
    "line": 2,
    "header_gray": "#e4e4e4",
    # ---- header (flow, centred blocks) ----
    "logo": {"mt": 10, "w": 216, "h": 172, "cx": 266.4},
    "title": {"font": "ar-light", "size": 44, "lh": 62, "mt": 14, "cx": 260.0, "sx": 1.0},
    "status": {"font": "ar-bold", "size": 30, "lh": 44, "mt": 34, "cx": 276.2, "sx": 1.0},
    "vatrow": {"h": 44, "mt": 24},
    "vat": {"font": "sans-bold", "size": 35, "lh": 40, "top": 0, "right": 566.2, "sx": 1.0},
    "vat_label": {"font": "ar-bold", "size": 19, "lh": 30, "top": 2, "right": 174.0, "sx": 1.0},
    "address": {"font": "ar", "size": 30, "lh": 44, "mt": 8, "cx": 283.1, "sx": 1.0},
    "simplified": {"font": "naskh-bold", "size": 30, "lh": 50, "mt": 8, "cx": 283.1, "sx": 1.0},
    # ---- meta rows (label right, value per group) ----
    "meta": {"mt": 60},
    "label": {"font": "ar-bold", "size": 20, "lh": 30, "right": 569.0, "sx": 1.0},
    "rows": {
        # h = row pitch; lt = label top in row; vt = value top in row
        "invoice": {"h": 51, "lt": 0, "vt": 0, "font": "sans-bold", "size": 37, "lh": 42, "cx": 210.9, "sx": 1.0},
        "type": {"h": 42, "lt": 0, "vt": 0, "font": "ar-bold", "size": 28, "lh": 40, "cx": 212.3, "sx": 1.0},
        "payment": {"h": 36, "lt": 0, "vt": 0, "font": "ar-bold", "size": 19, "lh": 30, "cx": 210.3, "sx": 1.0},
        "serial": {"h": 41, "lt": 0, "vt": 0, "font": "sans-bold", "size": 28, "lh": 34, "cx": 211.3, "sx": 1.0},
        "date": {"h": 36, "lt": 0, "vt": 0, "font": "narrow", "size": 32, "lh": 36, "right": 338.6, "sx": 1.0},
        "closed": {"h": 48, "lt": 0, "vt": 0, "font": "narrow", "size": 32, "lh": 36, "right": 339.1, "sx": 1.0},
        "note": {"h": 52, "lt": 0, "vt": 0, "font": "sans-bold", "size": 25, "lh": 30, "right": 341.1, "sx": 1.0},
        "customer": {"h": 46, "lt": 0, "vt": 0, "font": "ar-bold", "size": 21, "lh": 32, "cx": 248.7, "sx": 1.0},
        "phone": {"h": 40, "lt": 0, "vt": 0, "font": "sans-bold", "size": 26, "lh": 30, "cx": 249.6, "sx": 1.0},
    },
    # ---- table ----
    "table": {
        "mt": 0,
        "cols": [181.8, 80.1, 95.9, 98.8, 118.9],  # name, qty, unit, tax, total (right -> left)
        "head_h": 65,
        "row_h": 44,
        "th": {"font": "ar-bold", "size": 21, "lh": 23, "sx": 1.0},
        "name": {"font": "ar-bold", "size": 18, "lh": 22, "pad": 5, "pad_v": 4, "wrap": 158, "sx": 1.0},
        "num": {"font": "sans", "size": 22, "lh": 26, "sx": 1.0},
        "total_pad": 33,
    },
    # ---- totals ----
    "totals": {"mt": 12},
    "tlabel": {"font": "ar-bold", "size": 21, "lh": 30, "right": 566.0, "sx": 1.0},
    "trows": {
        "net": {"h": 53, "lt": 0, "vt": 0, "font": "narrow-bold", "size": 32, "lh": 34, "right": 275.2, "sx": 1.0},
        "discount": {"h": 46, "lt": 0, "vt": 0, "font": "narrow-bold", "size": 30, "lh": 34, "right": 275.2, "sx": 1.0},
        "tax": {"h": 70, "lt": 0, "vt": 0, "font": "narrow-bold", "size": 32, "lh": 34, "right": 274.2, "sx": 1.0},
        "total": {"h": 56, "lt": 0, "vt": 0, "font": "narrow-bold", "size": 39, "lh": 40, "right": 273.3, "sx": 1.0},
    },
    # ---- cashier, phone, QR ----
    "cashier": {"mt": 10, "label": {"font": "ar-bold", "size": 21, "lh": 30, "top": 20, "right": 559.3, "sx": 1.0},
                "name": {"font": "narrow", "size": 25, "lh": 26, "cx": 175.4, "sx": 1.0},
                "printed": {"font": "narrow", "size": 32, "lh": 34, "cx": 173.9, "sx": 1.0}},
    "phone": {"mt": 26, "lh": 46, "cx": 271.3,
              "label": {"font": "ar-bold", "size": 30, "sx": 1.0},
              "number": {"font": "sans-bold", "size": 41, "sx": 1.0}},
    "qr": {"mt": 76, "size": 240, "cx": 280.1, "mb": 24},
}


HEADER = """/*
 * فاتورة العميل بتصميم FERP — نسخة من فاتورة فرع المدينة المصوَّرة (10/2/2026 10:58 PM).
 *
 * ملف مولَّد: tools/receipt_calibration/ferp_css.py من spec.json. كل رقم هنا بكسل = نقطة طابعة،
 * مأخوذ من صورة FERP بعد تصحيح المنظور وتحجيمها حتى يملأ الجدول عرض الطباعة 576 نقطة (72 مم
 * على TM-T20III، مثل FERP). المعايرة تمت داخل نقاط البيع نفسها (htmlToCanvas) لا في صفحة.
 *
 * - الجذر بوزن id حتى لا تغلبه قواعد الثيم؛ font-family كلها !important لأن hosny_pos_theme
 *   يفرض «.pos * { font-family: Cairo !important }» و body نفسه يحمل class="pos".
 * - html-to-image يكتب كل font-size كـ floor(x) - 0.1، فالأحجام أعداد صحيحة.
 * - الاتجاه RTL ثابت في الحزمتين؛ الخصائص المنطقية لا يلمسها rtlcss، وكل خاصية فيزيائية
 *   يسبقها تعليق rtl:ignore على نفس السطر.
 * - scaleX يضبط عرض الخط على عرض خط FERP (الخطوط هنا بدائل حرة لخطوط ويندوز).
 * - كل النصوص سوداء #000 حتى تطبع واضحة (الرمادي الوحيد خلفية رأس الجدول، يُطبع نقاطاً كـ FERP).
 */"""


def load():
    if os.path.exists(SPEC_FILE):
        return json.load(open(SPEC_FILE))
    return copy.deepcopy(DEFAULT)


def save(spec):
    json.dump(spec, open(SPEC_FILE, "w"), indent=1, ensure_ascii=False)


def r1(v):
    return f"{round(v, 1):g}"


def font_decl(el):
    fam, weight = FACE[el["font"]]
    size = int(round(el["size"]))
    out = [f"font-family: {fam} !important;", f"font-size: {size}px;", f"font-weight: {weight};",
           f"line-height: {int(round(el['lh']))}px;" if "lh" in el else ""]
    return " ".join(x for x in out if x)


def sx_decl(el, origin):
    sx = el.get("sx", 1.0)
    if abs(sx - 1) < 0.005:
        return "transform: none;"
    return f"transform: scaleX({sx:.3f}); /*rtl:ignore*/transform-origin: {origin};"


def center_pad(cx, width):
    """padding that puts the centre of a full-width block at cx (physical px from the left)."""
    if cx <= width / 2:
        return f"padding-inline-start: {r1(width - 2 * cx)}px; padding-inline-end: 0;"   # RTL: start = right
    return f"padding-inline-start: 0; padding-inline-end: {r1(2 * cx - width)}px;"


def render(spec):
    W = spec["width"]
    R = ":is(#hosny-fr, .hosny-ferp-receipt)"
    L = [HEADER]
    a = L.append
    for fam, files in FONTS.items():
        for f, w in files:
            a(f'@font-face {{ font-family: "{fam}"; src: url("/hosny_pos_receipt/static/fonts/{f}") format("woff2"); '
              f'font-weight: {w}; font-style: normal; font-display: block; }}')
    a("")
    a(f"""{R} {{
    width: {W}px !important;
    max-width: none !important;
    margin: 0 !important;
    padding: 0 !important;
    background: #fff;
    color: #000 !important;
    /*rtl:ignore*/direction: rtl;
    text-align: start;
    font-family: "Hosny Receipt Arabic Bold", "Hosny Receipt Sans" !important;
    font-size: 20px;
    font-weight: 400;
    font-style: normal;
    line-height: 1;
    letter-spacing: 0;
    word-spacing: 0;
    text-transform: none;
    text-rendering: geometricPrecision;
    font-synthesis: none;
    overflow: hidden;
}}
/* أرقام وتواريخ بترتيبها اللاتيني داخل الفاتورة العربية */
{R} .hfr-ltr {{
    /*rtl:ignore*/direction: ltr;
    unicode-bidi: isolate;
}}
{R} * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    color: #000 !important;
    font-family: inherit !important;
    text-shadow: none !important;
}}""")
    lg = spec["logo"]
    a(f"""{R} .hfr-logo {{
    display: block;
    width: {r1(lg['w'])}px !important;
    height: {r1(lg['h'])}px !important;
    max-width: none !important;
    margin-top: {r1(lg['mt'])}px;
    margin-inline-start: {r1(W - lg['cx'] - lg['w'] / 2)}px;
    object-fit: fill;
    filter: grayscale(1) contrast({spec.get('logo_contrast', 1.6)});
}}""")
    for key, cls in (("title", "hfr-title"), ("status", "hfr-status"), ("address", "hfr-address"), ("simplified", "hfr-doc-title")):
        el = spec[key]
        a(f"""{R} .{cls} {{
    {font_decl(el)}
    margin-top: {r1(el['mt'])}px;
    {center_pad(el['cx'], W)}
    text-align: center;
    white-space: nowrap;
}}
{R} .{cls} > span {{ display: inline-block; {sx_decl(el, 'center')} }}""")
    vr = spec["vatrow"]
    a(f"""{R} .hfr-vat-row {{ position: relative; height: {r1(vr['h'])}px; margin-top: {r1(vr['mt'])}px; }}""")
    for key, cls in (("vat", "hfr-vat"), ("vat_label", "hfr-vat-label")):
        el = spec[key]
        a(f"""{R} .{cls} {{
    position: absolute;
    top: {r1(el['top'])}px;
    inset-inline-start: {r1(W - el['right'])}px;
    {font_decl(el)}
    white-space: nowrap;
    {sx_decl(el, '100% 50%')}
}}""")
    # meta + totals rows
    def rows(block_cls, block, label, rowspec, prefix):
        a(f"{R} .{block_cls} {{ margin-top: {r1(block['mt'])}px; }}")
        a(f"""{R} .{block_cls} .hfr-row {{ position: relative; }}
{R} .{block_cls} .hfr-label {{
    position: absolute;
    inset-inline-start: {r1(W - label['right'])}px;
    {font_decl(label)}
    white-space: nowrap;
    {sx_decl(label, '100% 50%')}
}}
{R} .{block_cls} .hfr-value > span {{ display: inline-block; max-width: 100%; overflow-wrap: anywhere; }}""")
        for name, el in rowspec.items():
            sel = f"{R} .{block_cls} .hfr-row-{name}"
            a(f"{sel} {{ min-height: {r1(el['h'])}px; }}")
            a(f"{sel} .hfr-label {{ top: {r1(el['lt'])}px; {sx_decl({'sx': el.get('lsx', 1.0)}, '100% 50%')} }}")
            if "cx" in el:
                horiz = center_pad(el["cx"], W) + " text-align: center;"
                origin = "center"
            else:
                horiz = f"padding-inline-start: {r1(W - el['right'])}px; padding-inline-end: 0; text-align: start;"
                origin = "100% 50%"
            a(f"""{sel} .hfr-value {{
    {font_decl(el)}
    {horiz}
}}
{sel} .hfr-value > span {{ position: relative; top: {r1(el['vt'])}px; {sx_decl(el, origin)} }}""")
    rows("hfr-meta", spec["meta"], spec["label"], spec["rows"], "")
    # table
    t = spec["table"]
    cw = t["cols"]
    a(f"""{R} table.hfr-table {{
    width: {W}px;
    margin-top: {r1(t['mt'])}px;
    border-collapse: collapse;
    border-spacing: 0;
    table-layout: fixed;
    background: transparent;
}}
{R} .hfr-table col.hfr-col-name {{ width: {r1(cw[0])}px; }}
{R} .hfr-table col.hfr-col-qty {{ width: {r1(cw[1])}px; }}
{R} .hfr-table col.hfr-col-unit {{ width: {r1(cw[2])}px; }}
{R} .hfr-table col.hfr-col-tax {{ width: {r1(cw[3])}px; }}
{R} .hfr-table col.hfr-col-total {{ width: {r1(cw[4])}px; }}
{R} .hfr-table th,
{R} .hfr-table td {{
    padding: 0;
    border: {spec['line']}px solid #000;
    vertical-align: middle;
    text-align: center;
    background-clip: padding-box;
}}
/* FERP: no outer border on the left (the total column), only the row lines */
{R} .hfr-table .hfr-c-total {{
    /*rtl:ignore*/border-left: 0;
    padding-inline-start: {r1(t['total_pad'])}px;
}}
{R} .hfr-table thead th {{
    height: {r1(t['head_h'])}px;
    background: {spec['header_gray']};
    {font_decl(t['th'])}
}}
{R} .hfr-table thead th span {{ display: block; {sx_decl(t['th'], 'center')} }}
{R} .hfr-table tbody td {{
    height: {r1(t['row_h'])}px;
    {font_decl(t['num'])}
}}
{R} .hfr-table tbody td > span {{ display: inline-block; {sx_decl(t['num'], 'center')} }}
{R} .hfr-table tbody td.hfr-c-name {{
    padding-block: {r1(t['name']['pad_v'])}px;
    padding-inline-start: {r1(t['name']['pad'])}px;
    padding-inline-end: 0;
    text-align: start;
    {font_decl(t['name'])}
    overflow-wrap: anywhere;
}}
{R} .hfr-table tbody td.hfr-c-name > span {{ display: block; width: {r1(t['name']['wrap'])}px; {sx_decl(t['name'], '100% 50%')} }}
{R} .hfr-table .hfr-line-detail {{ font-size: {int(round(t['name']['size'] * 0.85))}px; }}""")
    rows("hfr-totals", spec["totals"], spec["tlabel"], spec["trows"], "t")
    c = spec["cashier"]
    a(f"""{R} .hfr-cashier {{ position: relative; margin-top: {r1(c['mt'])}px; }}
{R} .hfr-cashier .hfr-label {{
    position: absolute;
    top: {r1(c['label']['top'])}px;
    inset-inline-start: {r1(W - c['label']['right'])}px;
    {font_decl(c['label'])}
    white-space: nowrap;
    {sx_decl(c['label'], '100% 50%')}
}}
{R} .hfr-cashier-name {{
    {font_decl(c['name'])}
    {center_pad(c['name']['cx'], W)}
    text-align: center;
    white-space: nowrap;
}}
{R} .hfr-cashier-name > span {{ display: inline-block; {sx_decl(c['name'], 'center')} }}
{R} .hfr-printed-at {{
    {font_decl(c['printed'])}
    {center_pad(c['printed']['cx'], W)}
    text-align: center;
    white-space: nowrap;
}}
{R} .hfr-printed-at > span {{ display: inline-block; {sx_decl(c['printed'], 'center')} }}""")
    p = spec["phone"]
    a(f"""{R} .hfr-phone {{
    margin-top: {r1(p['mt'])}px;
    line-height: {int(round(p['lh']))}px;
    {center_pad(p['cx'], W)}
    text-align: center;
    white-space: nowrap;
}}
{R} .hfr-phone-label {{ display: inline-block; {font_decl(p['label'])} }}
{R} .hfr-phone-number {{ display: inline-block; {font_decl(p['number'])} }}""")
    q = spec["qr"]
    a(f"""{R} .hfr-qr {{
    display: block;
    width: {r1(q['size'])}px !important;
    height: {r1(q['size'])}px !important;
    max-width: none !important;
    margin-top: {r1(q['mt'])}px;
    margin-bottom: {r1(q['mb'])}px;
    margin-inline-start: {r1(W - q['cx'] - q['size'] / 2)}px;
    image-rendering: pixelated;
}}""")
    a(f"""/* طباعة المتصفح (بدون طابعة ePOS): نفس مقاس فاتورة أودو هناك (266px) */
@media print {{
    {R} {{ zoom: {266 / W:.4f}; }}
}}""")
    css = "\n".join(L)
    return "\n".join(line for line in css.splitlines() if line.strip() != "") + "\n"


if __name__ == "__main__":
    print(render(load()))
