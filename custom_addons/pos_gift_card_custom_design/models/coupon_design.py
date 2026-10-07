# -*- coding: utf-8 -*-
"""Vector artwork for the Hosny A6 discount coupon.

The card is one inline ``<svg>`` drawn in the pixel grid of the approved
reference design (card from 13,36 to 722,528).  The viewBox adds the thin
page margin around it and has the A6 landscape ratio, so the PDF page, the
mail image and the browser preview all show the same artwork.

Only shapes live here - all wording and values are passed in by the caller.

QtWebKit (wkhtmltopdf) rasterises anything carrying ``opacity`` or a filter,
so the artwork uses neither: soft shadows are stacks of opaque shapes whose
colours are pre-blended with what lies under them, and every gradient stop
is opaque.  Text and ornaments therefore stay true vectors in the PDF.
"""
import math

VIEWBOX = (5, 24.8, 725, 514.4)
CARD = dict(x=13, y=36, w=709, h=492, r=22)
FRAME = dict(x=20.5, y=43.5, w=694, h=476.5, r=16)
FOOTER_TOP = 430

INK = "#2B200C"
INK_SOFT = "#4A3B22"
MUTED = "#6A5A3F"
GOLD = "#B49A62"
GOLD_DARK = "#8A7449"
BROWN = "#41351F"
CREAM_TEXT = "#ECE2CC"

# Left identity panel: the gold rule and the panel fill sit 7px apart with a
# light gap between them, as on the reference.
PANEL_RULE = (
    "M 198,36 C 240,36 264,67 264,113 V 338 "
    "C 264,384 242,414 204,438"
)
PANEL_FILL = (
    "M 13,36 H 184 C 228,36 257,67 257,114 V 336 "
    "C 257,380 236,409 198,433 L 198,440 H 13 Z"
)


def _f(value):
    """Compact number formatting for path data."""
    return ("%.2f" % value).rstrip("0").rstrip(".")


def _esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _star(cx, cy, points, outer, inner, rotate=-90.0):
    """Closed star polygon path."""
    parts = []
    for i in range(points * 2):
        radius = outer if i % 2 == 0 else inner
        angle = math.radians(rotate + i * 180.0 / points)
        parts.append("%s,%s" % (_f(cx + radius * math.cos(angle)),
                                _f(cy + radius * math.sin(angle))))
    return "M " + " L ".join(parts) + " Z"


def _star_tile(size, color, width):
    """One tile of the star lattice: a 16-point star with a ring at the centre
    and 10-point stars on the corners (drawn four times so they wrap)."""
    s = size / 73.0
    c = size / 2.0
    out = ['<g fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="miter">'
           % (color, _f(width))]
    out.append('<path d="%s"/>' % _star(c, c, 16, 28 * s, 17.5 * s))
    out.append('<circle cx="%s" cy="%s" r="%s"/>' % (_f(c), _f(c), _f(8 * s)))
    for x, y in ((0, 0), (size, 0), (0, size), (size, size)):
        out.append('<path d="%s"/>' % _star(x, y, 10, 15 * s, 7.8 * s))
    out.append("</g>")
    return "".join(out)


def _rosette_tile(size, color, width):
    """Faint rosette lattice of the main (cream) area."""
    c = size / 2.0
    s = size / 45.0
    petal = ("M 0,%s C %s,%s %s,%s 0,%s C %s,%s %s,%s 0,%s Z" % (
        _f(-4.6 * s), _f(3.2 * s), _f(-7 * s), _f(3.2 * s), _f(-11 * s), _f(-14.5 * s),
        _f(-3.2 * s), _f(-11 * s), _f(-3.2 * s), _f(-7 * s), _f(-4.6 * s)))
    out = ['<g fill="none" stroke="%s" stroke-width="%s">' % (color, _f(width))]
    out.append('<g transform="translate(%s,%s)">' % (_f(c), _f(c)))
    for i in range(12):
        out.append('<path d="%s" transform="rotate(%s)"/>' % (petal, i * 30))
    out.append('<circle r="%s"/></g>' % _f(3.4 * s))
    for x, y in ((0, 0), (size, 0), (0, size), (size, size)):
        out.append('<path d="%s"/>' % _star(x, y, 8, 6.5 * s, 3.2 * s))
    out.append("</g>")
    return "".join(out)


def _mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _shadow_rect(x, y, w, h, r, under, dark, spread=6.0, dy=3.0, steps=6):
    """Soft drop shadow from opaque rounded rects, darkest innermost."""
    out = []
    for i in range(steps):
        t = (i + 1) / float(steps)
        grow = spread * (1 - t)
        color = _mix(under, dark, t * t)
        out.append(
            '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s"/>'
            % (_f(x - grow), _f(y + dy - grow + 1), _f(w + 2 * grow),
               _f(h + 2 * grow - 1), _f(r + grow), color))
    return "".join(out)


def _shadow_circle(cx, cy, r, under, dark, spread=6.0, dy=3.0, steps=6):
    out = []
    for i in range(steps):
        t = (i + 1) / float(steps)
        out.append('<circle cx="%s" cy="%s" r="%s" fill="%s"/>'
                   % (_f(cx), _f(cy + dy), _f(r + spread * (1 - t)),
                      _mix(under, dark, t * t)))
    return "".join(out)


def _plaque(x0, y0, x1, y1, inset=0.0):
    """Value cartouche: concave corner notches and slightly bulging ends."""
    x0 += inset
    y0 += inset
    x1 -= inset
    y1 -= inset
    k = max(0.0, 1 - inset / 40.0)
    ch = 28 * k + 4          # chamfer run
    cv = 25 * k + 3          # chamfer rise
    rr = 4.5 * k + 1         # corner rounding
    my0 = y0 + cv
    my1 = y1 - cv
    pts = [
        "M %s,%s" % (_f(x0 + ch + rr), _f(y0)),
        "H %s" % _f(x1 - ch - rr),
        "Q %s,%s %s,%s" % (_f(x1 - ch), _f(y0), _f(x1 - ch + rr * .7), _f(y0 + rr * .7)),
        "Q %s,%s %s,%s" % (_f(x1 - ch * .86), _f(my0 - cv * .13), _f(x1 - 3 - rr * .7), _f(my0 - rr * .7)),
        "Q %s,%s %s,%s" % (_f(x1 - 3), _f(my0), _f(x1 - 2), _f(my0 + rr * 1.4)),
        "C %s,%s %s,%s %s,%s" % (_f(x1 + .6), _f(my0 + 12), _f(x1 + .6), _f(my1 - 12),
                                 _f(x1 - 2), _f(my1 - rr * 1.4)),
        "Q %s,%s %s,%s" % (_f(x1 - 3), _f(my1), _f(x1 - 3 - rr * .7), _f(my1 + rr * .7)),
        "Q %s,%s %s,%s" % (_f(x1 - ch * .86), _f(my1 + cv * .13), _f(x1 - ch + rr * .7), _f(y1 - rr * .7)),
        "Q %s,%s %s,%s" % (_f(x1 - ch), _f(y1), _f(x1 - ch - rr), _f(y1)),
        "H %s" % _f(x0 + ch + rr),
        "Q %s,%s %s,%s" % (_f(x0 + ch), _f(y1), _f(x0 + ch - rr * .7), _f(y1 - rr * .7)),
        "Q %s,%s %s,%s" % (_f(x0 + ch * .86), _f(my1 + cv * .13), _f(x0 + 3 + rr * .7), _f(my1 + rr * .7)),
        "Q %s,%s %s,%s" % (_f(x0 + 3), _f(my1), _f(x0 + 2), _f(my1 - rr * 1.4)),
        "C %s,%s %s,%s %s,%s" % (_f(x0 - .6), _f(my1 - 12), _f(x0 - .6), _f(my0 + 12),
                                 _f(x0 + 2), _f(my0 + rr * 1.4)),
        "Q %s,%s %s,%s" % (_f(x0 + 3), _f(my0), _f(x0 + 3 + rr * .7), _f(my0 - rr * .7)),
        "Q %s,%s %s,%s" % (_f(x0 + ch * .86), _f(my0 - cv * .13), _f(x0 + ch - rr * .7), _f(y0 + rr * .7)),
        "Q %s,%s %s,%s Z" % (_f(x0 + ch), _f(y0), _f(x0 + ch + rr), _f(y0)),
    ]
    return " ".join(pts)


def _sparkle(cx, cy, color):
    """Four tapered petals set as an X, flanking the amount."""
    petal = "M 0,0 C 2.1,-2 2.2,-5.4 0,-8.4 C -2.2,-5.4 -2.1,-2 0,0 Z"
    return ('<g transform="translate(%s,%s)" fill="%s">%s</g>' % (
        _f(cx), _f(cy), color,
        "".join('<path d="%s" transform="rotate(%s)"/>' % (petal, a)
                for a in (45, 135, 225, 315))))


def _cloche(cx):
    """Serving cloche with a bow, between the two header rules."""
    return (
        '<g stroke="#85714A" stroke-width="0.8" fill="url(#hcCloche)">'
        '<ellipse cx="%(l)s" cy="73.2" rx="3.6" ry="1.9" transform="rotate(-12 %(l)s 73.2)"/>'
        '<ellipse cx="%(r)s" cy="73.2" rx="3.6" ry="1.9" transform="rotate(12 %(r)s 73.2)"/>'
        '<circle cx="%(c)s" cy="74.4" r="1.5"/>'
        '<path d="M %(c)s,75.8 V 77.4" fill="none"/>'
        '<path d="M %(dl)s,91.2 C %(dl)s,82.4 %(dl2)s,77.4 %(c)s,77.4 '
        'C %(dr2)s,77.4 %(dr)s,82.4 %(dr)s,91.2 Z"/>'
        '<rect x="%(bl)s" y="91" width="35" height="4.6" rx="2.2"/>'
        '</g>' % dict(c=_f(cx), l=_f(cx - 3.6), r=_f(cx + 3.6),
                      dl=_f(cx - 15.6), dl2=_f(cx - 8.6), dr=_f(cx + 15.6),
                      dr2=_f(cx + 8.6), bl=_f(cx - 17.5)))


def _calendar(x, y):
    """Outline calendar centred on x,y (14 x 14)."""
    dots = "".join('<circle cx="%s" cy="%s" r="0.95"/>' % (_f(x + dx), _f(y + dy))
                   for dx, dy in ((-3.4, 1.4), (0, 1.4), (3.4, 1.4), (-3.4, 4.4), (0, 4.4)))
    return (
        '<g fill="none" stroke="#8D774C" stroke-width="1.5" stroke-linecap="round">'
        '<rect x="%s" y="%s" width="14" height="13" rx="2.4"/>'
        '<path d="M %s,%s H %s"/>'
        '<path d="M %s,%s V %s"/><path d="M %s,%s V %s"/></g>'
        '<g fill="#8D774C">%s</g>' % (
            _f(x - 7), _f(y - 5.6), _f(x - 7), _f(y - 1.6), _f(x + 7),
            _f(x - 3.6), _f(y - 7.6), _f(y - 4), _f(x + 3.6), _f(y - 7.6), _f(y - 4),
            dots))


PHONE_GLYPH = (
    "M6.62,10.79 c1.44,2.83 3.76,5.15 6.59,6.59 l2.2,-2.2 "
    "c0.27,-0.27 0.67,-0.36 1.02,-0.24 1.12,0.37 2.33,0.57 3.57,0.57 "
    "0.55,0 1,0.45 1,1 V20 c0,0.55 -0.45,1 -1,1 -9.39,0 -17,-7.61 -17,-17 "
    "0,-0.55 0.45,-1 1,-1 h3.5 c0.55,0 1,0.45 1,1 0,1.25 0.2,2.45 0.57,3.57 "
    "0.11,0.35 0.03,0.74 -0.25,1.02 l-2.2,2.2 Z"
)


def _phone(cx, cy):
    s = 0.56
    return ('<path d="%s" fill="%s" transform="translate(%s,%s) scale(%s)"/>'
            % (PHONE_GLYPH, INK, _f(cx - 12 * s), _f(cy - 12 * s), s))


def _mail(cx, cy):
    return (
        '<g fill="none" stroke="%s" stroke-width="1.2" stroke-linejoin="round">'
        '<rect x="%s" y="%s" width="11.4" height="8.4" rx="1.2"/>'
        '<path d="M %s,%s L %s,%s L %s,%s"/></g>' % (
            INK, _f(cx - 5.7), _f(cy - 4.2),
            _f(cx - 4.8), _f(cy - 3), _f(cx), _f(cy + .6), _f(cx + 4.8), _f(cy - 3)))


def _pin(cx, cy):
    """Outline map pin: a teardrop with a ring, point at the bottom."""
    return (
        '<g fill="none" stroke="#33281A" stroke-width="1.35" transform="translate(%s,%s)">'
        '<path d="M 0,6.8 C -2.6,3.6 -4.9,0.4 -4.9,-1.8 C -4.9,-4.6 -2.7,-6.6 0,-6.6 '
        'C 2.7,-6.6 4.9,-4.6 4.9,-1.8 C 4.9,0.4 2.6,3.6 0,6.8 Z"/>'
        '<circle cx="0" cy="-1.9" r="1.9"/></g>' % (_f(cx), _f(cy)))


def _emblem(cx, cy, color):
    """The small boat-and-anchor mark in the middle of the footer."""
    return (
        '<g fill="none" stroke="%(c)s" stroke-width="1.1" stroke-linecap="round" '
        'stroke-linejoin="round" transform="translate(%(x)s,%(y)s)">'
        '<path d="M -22.6,-9.2 C -13,-9.6 -5,-10.6 0,-13.8 C 5,-10.6 13,-9.6 22.6,-9.2 '
        'C 17,-1 9,3.2 0,3.4 C -9,3.2 -17,-1 -22.6,-9.2 Z"/>'
        '<circle cx="0" cy="-7.4" r="2"/>'
        '<path d="M 0,0 V 13.6"/><path d="M -2.6,4.6 H 2.6"/>'
        '<path d="M -10.4,6.8 L 0,13.6 L 10.4,6.8"/></g>' % dict(
            c=color, x=_f(cx), y=_f(cy)))


def wrap_branches(branches, max_chars=27, max_lines=2, separator=" • "):
    """Lay branch names out over at most ``max_lines`` footer lines.

    Anything that will not fit is summarised as a trailing "+N" so a company
    that keeps opening branches never overflows the card.
    """
    names = [str(b).strip() for b in branches or [] if str(b).strip()]
    if not names:
        return []
    lines, current, used = [], "", 0
    for name in names:
        candidate = (current + separator + name) if current else name
        if current and len(candidate) > max_chars:
            if len(lines) == max_lines - 1:
                break
            lines.append(current)
            current, candidate = name, name
        current = candidate
        used += 1
    if current:
        lines.append(current)
    remaining = len(names) - used
    if remaining > 0:
        lines[-1] = "%s +%d" % (lines[-1], remaining)
    return lines


def barcode_modules(pattern):
    """reportlab's decomposed Code128 ("BaAbC…": upper = bar, lower = space,
    a-d = 1-4 modules) as (start, width) bars in module units, plus the total."""
    bars, pos = [], 0
    for char in pattern or "":
        width = ord(char.lower()) - 96
        if char.isupper():
            bars.append((pos, width))
        pos += width
    return bars, pos


def _barcode(pattern, x, y, w, h, color):
    bars, total = barcode_modules(pattern)
    if not bars or not total:
        return ""
    unit = w / float(total)
    return '<g fill="%s">%s</g>' % (color, "".join(
        '<rect x="%s" y="%s" width="%s" height="%s"/>'
        % (_f(x + start * unit), _f(y), _f(width * unit), _f(h))
        for start, width in bars))


def build_card_svg(brand, tagline, headline, subtitle, value_label, amount,
                   currency, expiry, expiry_label, code, code_title, code_hint_1,
                   code_hint_2, branches_label, branches, phones, email,
                   logo_src=None, barcode_pattern=None, font_family="HosnyCoupon",
                   serif_family="HosnyCouponSerif",
                   barcode_missing="الباركود غير متاح", **_ignored):
    """Return the complete coupon as one inline SVG string."""
    ff = font_family
    sf = serif_family

    def text(x, y, size, weight, fill, value, anchor="middle", rtl=True, extra=""):
        return (
            '<text x="%s" y="%s" font-family="%s" font-weight="%s" font-size="%s" '
            'fill="%s" text-anchor="%s"%s%s>%s</text>'
            % (_f(x), _f(y), ff, weight, _f(size), fill, anchor,
               ' direction="rtl"' if rtl else "", extra, _esc(value)))

    # ── footer contacts ──
    rows = []
    contacts = [("phone", p) for p in list(phones or [])[:3]]
    if email:
        contacts.append(("mail", email))
    for index, (kind, value) in enumerate(contacts):
        mid = 448.2 + index * 20.7
        rows.append(_phone(50.2, mid) if kind == "phone" else _mail(50.2, mid))
        rows.append(text(65, mid + 4.1, 12.1, 700, INK, value, anchor="start", rtl=False))

    branch_rows = "".join(
        text(667.6, 494.4 + i * 15.5, 11.4, 600, INK_SOFT, line, anchor="start")
        for i, line in enumerate(wrap_branches(branches)))

    # ── logo ──
    if logo_src:
        logo = ('<image xlink:href="%s" href="%s" x="97" y="68" width="76" height="76" '
                'preserveAspectRatio="xMidYMid slice" clip-path="url(#hcLogoClip)"/>'
                % (logo_src, logo_src))
    else:
        logo = ('<circle cx="135" cy="106" r="31" fill="none" stroke="%s" stroke-width="1.6"/>'
                % GOLD)

    if barcode_pattern:
        barcode = _barcode(barcode_pattern, 328, 353, 216, 42, "#2E2410")
    else:
        barcode = text(436, 380, 13, 700, MUTED, barcode_missing)

    rule_l = '<path d="M 367,83.5 H 447" stroke="url(#hcRuleL)" stroke-width="1.1"/>'
    rule_r = '<path d="M 525,83.5 H 607" stroke="url(#hcRuleR)" stroke-width="1.1"/>'

    return """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="{vb}" preserveAspectRatio="xMidYMid meet">
  <defs>
    <clipPath id="hcCardClip"><rect x="13" y="36" width="709" height="492" rx="22"/></clipPath>
    <clipPath id="hcPanelClip"><path d="{panel_fill}"/></clipPath>
    <clipPath id="hcLogoClip"><circle cx="135" cy="106" r="38"/></clipPath>
    <linearGradient id="hcPage" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F8F2E3"/><stop offset="1" stop-color="#EAE1CC"/>
    </linearGradient>
    <linearGradient id="hcMain" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FAF5EA"/><stop offset="0.55" stop-color="#F8F2E5"/>
      <stop offset="1" stop-color="#F3EBDA"/>
    </linearGradient>
    <linearGradient id="hcPanel" gradientUnits="userSpaceOnUse" x1="13" y1="0" x2="257" y2="0">
      <stop offset="0" stop-color="#E6DABD"/><stop offset="0.45" stop-color="#ECE2C7"/>
      <stop offset="0.8" stop-color="#E7DBBF"/><stop offset="1" stop-color="#D8CAA8"/>
    </linearGradient>
    <linearGradient id="hcFooter" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#EBE0C5"/><stop offset="0.5" stop-color="#E9DDC0"/>
      <stop offset="1" stop-color="#E4D8BA"/>
    </linearGradient>
    <linearGradient id="hcChip" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFDF7"/><stop offset="1" stop-color="#F6EFDF"/>
    </linearGradient>
    <linearGradient id="hcCal" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F4EAD2"/><stop offset="1" stop-color="#E8D9B6"/>
    </linearGradient>
    <linearGradient id="hcCloche" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#CDB580"/><stop offset="1" stop-color="#A48F60"/>
    </linearGradient>
    <linearGradient id="hcRuleL" gradientUnits="userSpaceOnUse" x1="367" y1="0" x2="447" y2="0">
      <stop offset="0" stop-color="#E4D8BE"/><stop offset="1" stop-color="#A89366"/>
    </linearGradient>
    <linearGradient id="hcRuleR" gradientUnits="userSpaceOnUse" x1="525" y1="0" x2="607" y2="0">
      <stop offset="0" stop-color="#A89366"/><stop offset="1" stop-color="#E4D8BE"/>
    </linearGradient>
    <linearGradient id="hcDivider" gradientUnits="userSpaceOnUse" x1="112" y1="0" x2="156" y2="0">
      <stop offset="0" stop-color="#E6DABE"/><stop offset="0.5" stop-color="#4E3F26"/>
      <stop offset="1" stop-color="#E6DABE"/>
    </linearGradient>
    <linearGradient id="hcRim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#D9C799"/><stop offset="0.5" stop-color="#C9B482"/>
      <stop offset="1" stop-color="#BDA672"/>
    </linearGradient>
    <linearGradient id="hcBrown" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4D4029"/><stop offset="0.35" stop-color="#3F331E"/>
      <stop offset="0.55" stop-color="#4A3E28"/><stop offset="1" stop-color="#372C19"/>
    </linearGradient>
    <linearGradient id="hcAmount" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#E4DCC8"/><stop offset="1" stop-color="#A69A7E"/>
    </linearGradient>
    <linearGradient id="hcBox" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFEF9"/><stop offset="1" stop-color="#FAF6EC"/>
    </linearGradient>
    <pattern id="hcMainPat" x="289.5" y="36.5" width="45" height="45" patternUnits="userSpaceOnUse">{main_tile}</pattern>
    <pattern id="hcPanelPat" x="13.5" y="37.5" width="73" height="73" patternUnits="userSpaceOnUse">{panel_tile}</pattern>
    <pattern id="hcFootPat" x="136" y="429" width="62" height="62" patternUnits="userSpaceOnUse">{foot_tile}</pattern>
  </defs>

  <rect x="{vx}" y="{vy}" width="{vw}" height="{vh}" fill="url(#hcPage)"/>
  {card_shadow}
  <g clip-path="url(#hcCardClip)">
    <rect x="13" y="36" width="709" height="492" fill="url(#hcMain)"/>
    <rect x="13" y="36" width="709" height="492" fill="url(#hcMainPat)"/>

    <!-- left identity panel -->
    <path d="{panel_rule} L 13,438 V 36 Z" fill="#FCF6E7"/>
    <path d="{panel_fill}" fill="url(#hcPanel)"/>
    <rect x="13" y="36" width="260" height="410" fill="url(#hcPanelPat)" clip-path="url(#hcPanelClip)"/>
    <path d="{panel_rule}" fill="none" stroke="#A0957D" stroke-width="1.1"/>

    <!-- footer band -->
    <rect x="13" y="{ft}" width="709" height="{fh}" fill="url(#hcFooter)"/>
    <rect x="13" y="{ft}" width="709" height="{fh}" fill="url(#hcFootPat)"/>
    <path d="M 13,{ft_hi} H 722" stroke="#FBF6EA" stroke-width="2"/>
    <path d="M 13,{ft_line} H 722" stroke="#D3C7AF" stroke-width="1"/>

    <rect x="{fx}" y="{fy}" width="{fw}" height="{fhh}" rx="{fr}" fill="none"
          stroke="#BDB196" stroke-width="1"/>
  </g>
  <rect x="13.5" y="36.5" width="708" height="491" rx="21.5" fill="none"
        stroke="#DCD1BA" stroke-width="1"/>

  <!-- logo -->
  {logo_shadow}
  <circle cx="135" cy="106" r="41" fill="#FCF4E4" stroke="#9C8E71" stroke-width="0.9"/>
  {logo}

  {brand}
  {tagline}
  <path d="M 112,250 H 156" stroke="url(#hcDivider)" stroke-width="1.6" stroke-linecap="round"/>

  <!-- validity chip -->
  {chip_shadow}
  <rect x="38" y="258" width="245" height="54" rx="10" fill="url(#hcChip)" stroke="#D6CAB0" stroke-width="0.9"/>
  <rect x="237.5" y="269" width="32.5" height="32.5" rx="7.5" fill="url(#hcCal)" stroke="#CDBB93" stroke-width="0.9"/>
  {calendar}
  {expiry_label}
  {expiry}

  <!-- headline -->
  {rule_l}
  <circle cx="451.2" cy="83.5" r="2.3" fill="#A48F60"/>
  {cloche}
  <circle cx="521.2" cy="83.5" r="2.3" fill="#A48F60"/>
  {rule_r}
  {headline}
  {subtitle}

  <!-- value cartouche -->
  {cart_shadow}
  <path d="{cart_outer}" fill="url(#hcRim)" stroke="#AE9864" stroke-width="0.8"/>
  <path d="{cart_dark}" fill="url(#hcBrown)"/>
  <path d="{cart_rule}" fill="none" stroke="#8C7C5B" stroke-width="0.9"/>
  {spark_l}
  {spark_r}
  {value_label}
  <text x="485" y="288" font-family="{sf}" font-weight="600" font-size="{amount_size}"
        letter-spacing="1" fill="url(#hcAmount)" text-anchor="middle">{amount}</text>
  {currency}

  <!-- barcode -->
  {box_shadow}
  <rect x="287" y="345" width="298" height="80" rx="9" fill="url(#hcBox)" stroke="#DED6C3" stroke-width="0.8"/>
  {barcode}
  <text x="435.5" y="416.4" font-family="{sf}" font-weight="600" font-size="15.2"
        letter-spacing="1.4" fill="#33281A" text-anchor="middle">{code}</text>
  {code_title}
  {hint1}
  {hint2}

  <!-- footer content -->
  {rows}
  {emblem}
  {pin}
  {branches_label}
  {branch_rows}
</svg>""".format(
        vb=" ".join(_f(v) for v in VIEWBOX),
        vx=_f(VIEWBOX[0]), vy=_f(VIEWBOX[1]), vw=_f(VIEWBOX[2]), vh=_f(VIEWBOX[3]),
        panel_fill=PANEL_FILL, panel_rule=PANEL_RULE,
        main_tile=_rosette_tile(45, "#F0E9DA", 0.7),
        panel_tile=_star_tile(73, "#CDBF9F", 0.9),
        foot_tile=_star_tile(62, "#D3C5A6", 0.85),
        card_shadow=_shadow_rect(13, 36, 709, 492, 22, "#EAE1CC", "#CFC2A6", spread=9, dy=5),
        ft=FOOTER_TOP, fh=CARD["y"] + CARD["h"] - FOOTER_TOP,
        ft_hi=_f(FOOTER_TOP - 2), ft_line=_f(FOOTER_TOP - 0.5),
        fx=FRAME["x"], fy=FRAME["y"], fw=FRAME["w"], fhh=FRAME["h"], fr=FRAME["r"],
        logo_shadow=_shadow_circle(135, 106, 41, "#E6DBBF", "#B9AA88", spread=5, dy=2.6),
        logo=logo,
        # 13 characters fill the panel at the design size; longer names shrink.
        brand=text(135.5, 205, 23.5 * min(1.0, 13.0 / max(len(str(brand or "")), 1)),
                   900, INK, brand),
        tagline=text(135, 232.5, 12.1, 600, "#5B4C33", tagline),
        chip_shadow=_shadow_rect(38, 258, 245, 54, 10, "#E7DCC0", "#D8CCB0", spread=7, dy=2),
        calendar=_calendar(253.75, 286),
        expiry_label=text(224.5, 278.6, 10.5, 600, "#5B4C33", expiry_label, anchor="start"),
        expiry=text(223.6, 295.2, 14, 800, INK, expiry, anchor="end", rtl=False),
        rule_l=rule_l, rule_r=rule_r, cloche=_cloche(487),
        headline=text(485.5, 160, 49.1, 900, INK, headline),
        subtitle=text(485, 189.2, 16.4, 600, INK_SOFT, subtitle),
        cart_shadow=_shadow_rect(352, 214, 271, 115, 30, "#F4ECDD", "#D6C9AC", spread=8, dy=3),
        cart_outer=_plaque(341, 208, 634, 327),
        cart_dark=_plaque(341, 208, 634, 327, 5.5),
        cart_rule=_plaque(341, 208, 634, 327, 10.5),
        spark_l=_sparkle(363.5, 268, "#D9CDB2"), spark_r=_sparkle(611.5, 268, "#D9CDB2"),
        value_label=text(486, 232.6, 11.9, 700, CREAM_TEXT, value_label),
        sf=sf, amount_size=_f(52.7 if len(str(amount)) <= 7 else max(34, 52.7 - 5 * (len(str(amount)) - 7))),
        amount=_esc(amount),
        currency=text(486, 309, 14.4, 800, "#EFE6D2", currency),
        box_shadow=_shadow_rect(287, 345, 298, 80, 9, "#F3EBDB", "#DDD2BA", spread=6, dy=2.5),
        barcode=barcode, code=_esc(code),
        code_title=text(685.6, 374, 13.5, 800, INK, code_title, anchor="start"),
        hint1=text(685.6, 391.6, 10.8, 600, MUTED, code_hint_1, anchor="start"),
        hint2=text(685.6, 407.6, 11, 600, MUTED, code_hint_2, anchor="start"),
        rows="\n  ".join(rows),
        emblem=_emblem(367.8, 502.5, "#C2B394"),
        pin=_pin(684.8, 470.6),
        branches_label=text(668, 476, 14.2, 800, INK, branches_label, anchor="start"),
        branch_rows=branch_rows,
    )
