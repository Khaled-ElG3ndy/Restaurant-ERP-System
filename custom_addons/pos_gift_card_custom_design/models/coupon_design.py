# -*- coding: utf-8 -*-
"""Vector artwork for the Hosny A6 discount coupon.

The whole card is emitted as a single inline ``<svg>`` drawn on a fixed
1489 x 1039 grid (A6 landscape at ~10 units per millimetre).  Working on one
grid keeps every ornament, box and baseline in exact proportion whatever size
the page is finally rendered at, and it renders identically in wkhtmltopdf and
in the browser preview.

Only shapes live here - all wording and values are passed in by the caller.
"""

INK = "#2B210F"
BROWN = "#453824"
BROWN_DARK = "#332817"
BROWN_INNER = "#5C4B30"
GOLD = "#B79A5A"
GOLD_BRIGHT = "#D4C5A5"
GOLD_SOFT = "#C7AA6B"
GOLD_TEXT = "#A98234"
GOLD_MUTED = "#A88340"
CREAM = "#F3EADB"
PAGE = "#E9DEC6"
PANEL = "#E4D7BC"
CHIP = "#FFF9EA"
BORDER = "#D0C1A7"
PATTERN = "#DDD3BE"
PANEL_PATTERN = "#CFC2A9"
# QtWebKit rasterises any group carrying an "opacity" attribute, which would
# print the ornaments as soft bitmaps.  These are the same tints pre-blended
# against their backdrop, so every stroke stays true vector in the PDF.
GOLD_ON_PANEL = "#CABCA2"      # left panel watermark
GOLD_ON_FOOTER = "#C7B89D"     # footer arabesque
GOLD_ON_BROWN = "#746446"      # cartouche inner rule
GOLD_ON_CREAM_55 = "#DEC693"   # barcode divider

# The card sits on the page with a tiny margin so its rounded corners show.
CARD = dict(x=6, y=24, w=1477, h=985, r=46)

# Left cream brand panel with the same soft sweep as the reference design.
LEFT_PANEL = (
    "M 6,70 Q 6,34 43,34 H 386 C 478,34 527,112 527,203 V 644 "
    "C 527,742 478,803 391,844 C 265,902 145,952 6,1006 Z"
)
LEFT_EDGE = (
    "M 386,34 C 482,34 540,113 540,205 V 647 "
    "C 540,751 488,815 399,856 C 272,914 148,963 6,1018"
)
LEFT_EDGE_INNER = (
    "M 374,34 C 463,40 510,116 510,204 V 636 "
    "C 510,727 465,785 382,825 C 257,883 142,930 6,985"
)
FOOTER_TOP = 825

# Classic shamsa cartouche: flat top and bottom, concave shoulders, lobed ends.
CARTOUCHE = (
    "M 720,420 H 1088 C 1137,420 1160,438 1171,467 "
    "C 1180,490 1190,503 1204,515 C 1216,526 1216,564 1204,575 "
    "C 1190,587 1180,600 1171,623 C 1160,652 1137,670 1088,670 "
    "H 720 C 671,670 648,652 637,623 C 628,600 618,587 604,575 "
    "C 592,564 592,526 604,515 C 618,503 628,490 637,467 "
    "C 648,438 671,420 720,420 Z"
)


def _rot(deg):
    return 'transform="rotate(%s)"' % deg


def _mandala(transform="", color=GOLD):
    """12-fold geometric medallion centred on the origin, radius 100."""
    out = ['<g transform="%s" fill="none" stroke="%s" stroke-width="4">'
           % (transform, color)]
    for r in (99, 86, 60, 24):
        out.append('<circle r="%s"/>' % r)
    for i in range(12):
        out.append('<path d="M 0,-26 C 15,-38 15,-50 0,-60 C -15,-50 -15,-38 0,-26 Z" %s/>'
                   % _rot(i * 30))
    for i in range(24):
        out.append('<path d="M 0,-61 L 0,-85" %s/>' % _rot(i * 15 + 7.5))
    for i in range(12):
        out.append('<circle cx="0" cy="-72" r="5" fill="%s" stroke="none" %s/>'
                   % (color, _rot(i * 30)))
    out.append("</g>")
    return "\n".join(out)


def _floral(transform="", color=GOLD):
    """Wide, flat arabesque fan used as the footer watermark.

    Sized to sit wholly inside the footer band so it needs no clip path.
    """
    petal = "M 0,-10 C 24,-26 34,-54 0,-84 C -34,-54 -24,-26 0,-10 Z"
    mid = "M 0,-10 C 22,-22 34,-42 26,-64 C 4,-56 -4,-32 0,-10 Z"
    out = ['<g transform="%s" fill="none" stroke="%s" stroke-width="4">'
           % (transform, color)]
    out.append('<path d="%s"/>' % petal)
    for sx in (1, -1):
        out.append('<g transform="scale(%s,1)"><path d="%s"/>'
                   '<path d="%s" transform="rotate(34)"/></g>' % (sx, mid, mid))
    out.append('<path d="M -118,6 C -74,-16 -34,-4 0,-8 C 34,-4 74,-16 118,6"/>')
    out.append('<path d="M -96,20 C -52,2 -18,12 0,10 C 18,12 52,2 96,20"/>')
    out.append('<circle cx="0" cy="-4" r="11" fill="%s" stroke="none"/>' % color)
    out.append("</g>")
    return "\n".join(out)


def _sprig(transform=""):
    """Little gold leaf flourish flanking the value cartouche."""
    leaf = "M 0,0 C 12,-6 26,-4 36,6 C 24,14 10,12 0,0 Z"
    out = ['<g transform="%s" fill="%s">' % (transform, GOLD)]
    for a in (-52, 0, 52):
        out.append('<path d="%s" %s/>' % (leaf, _rot(a)))
    out.append('<circle cx="-9" cy="0" r="6"/>')
    out.append("</g>")
    return "\n".join(out)


def _ring_icon(cx, cy, glyph, r=16):
    """A gold outline circle with a filled 24x24 glyph centred inside it."""
    return (
        '<g><circle cx="%s" cy="%s" r="%s" fill="none" stroke="%s" stroke-width="2.4"/>'
        '<g transform="translate(%s,%s) scale(0.72)"><path d="%s" fill="%s"/></g></g>'
        % (cx, cy, r, GOLD, cx - 8.6, cy - 8.6, glyph, GOLD)
    )


PHONE_GLYPH = (
    "M6.62,10.79 c1.44,2.83 3.76,5.15 6.59,6.59 l2.2,-2.2 "
    "c0.27,-0.27 0.67,-0.36 1.02,-0.24 1.12,0.37 2.33,0.57 3.57,0.57 "
    "0.55,0 1,0.45 1,1 V20 c0,0.55 -0.45,1 -1,1 -9.39,0 -17,-7.61 -17,-17 "
    "0,-0.55 0.45,-1 1,-1 h3.5 c0.55,0 1,0.45 1,1 0,1.25 0.2,2.45 0.57,3.57 "
    "0.11,0.35 0.03,0.74 -0.25,1.02 l-2.2,2.2 Z"
)
MAIL_GLYPH = (
    "M20,4 H4 C2.9,4 2.01,4.9 2.01,6 L2,18 c0,1.1 0.9,2 2,2 h16 "
    "c1.1,0 2,-0.9 2,-2 V6 C22,4.9 21.1,4 20,4 Z M20,8 l-8,5 -8,-5 V6 l8,5 8,-5 V8 Z"
)


def _pin_icon(cx, cy, s=1.0):
    return (
        '<g transform="translate(%s,%s) scale(%s)">'
        '<path d="M 0,-20 C -10.5,-20 -19,-11.5 -19,-1 C -19,13 0,26 0,26 '
        'C 0,26 19,13 19,-1 C 19,-11.5 10.5,-20 0,-20 Z" fill="none" '
        'stroke="%s" stroke-width="3.2"/>'
        '<circle cx="0" cy="-1" r="6.6" fill="none" stroke="%s" stroke-width="3.2"/></g>'
        % (cx, cy, s, GOLD, GOLD)
    )


def _plain_icon(cx, cy, glyph, color=INK, scale=0.72):
    return (
        '<g transform="translate(%s,%s) scale(%s)">'
        '<path d="%s" fill="%s"/></g>'
        % (cx - 12 * scale, cy - 12 * scale, scale, glyph, color)
    )


def _pattern_defs():
    return """
    <pattern id="hosnySoftPattern" width="92" height="92" patternUnits="userSpaceOnUse">
      {soft}
    </pattern>
    <pattern id="hosnyPanelPattern" width="96" height="96" patternUnits="userSpaceOnUse">
      {panel}
    </pattern>
    """.format(
        soft=_mandala("translate(46,46) scale(0.31)", PATTERN),
        panel=_mandala("translate(48,48) scale(0.38)", PANEL_PATTERN),
    )


def _calendar_icon(cx, cy):
    return (
        '<g transform="translate(%s,%s)" fill="none" stroke="%s" stroke-width="3.4" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<rect x="-21" y="-16" width="42" height="37" rx="6"/>'
        '<path d="M -21,-4 H 21"/>'
        '<path d="M -11,-22 V -11"/><path d="M 11,-22 V -11"/>'
        '<path d="M -11,6 H -9"/><path d="M -1,6 H 1"/><path d="M 9,6 H 11"/>'
        '<path d="M -11,14 H -9"/><path d="M -1,14 H 1"/></g>' % (cx, cy, GOLD)
    )


def _cloche(cx, cy):
    """Gold cloche (domed serving dish) with a sprig on top."""
    return (
        '<g transform="translate(%s,%s)" fill="%s">'
        '<path d="M 0,-38 C -13,-40 -25,-50 -29,-64 C -14,-67 -2,-56 0,-38 Z"/>'
        '<path d="M 0,-38 C 13,-40 25,-50 29,-64 C 14,-67 2,-56 0,-38 Z"/>'
        '<path d="M 0,-40 L 0,-26" stroke="%s" stroke-width="6" stroke-linecap="round"/>'
        '<circle cx="0" cy="-28" r="7.5"/>'
        '<path d="M -55,22 C -55,-8 -30,-24 0,-24 C 30,-24 55,-8 55,22 Z"/>'
        '<rect x="-68" y="26" width="136" height="12" rx="6"/></g>'
        % (cx, cy, GOLD, GOLD)
    )


def _esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


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


def build_card_svg(brand, tagline, headline, subtitle, value_label, amount,
                   currency, expiry, expiry_label, code, code_title, code_hint_1,
                   code_hint_2, branches_label, branches, phones, email,
                   logo_src=None, barcode_src=None, font_family="HosnyCoupon",
                   barcode_missing="الباركود غير متاح"):
    """Return the complete coupon as one inline SVG string."""
    rows = []
    for index, number in enumerate(list(phones)[:3]):
        baseline = 884 + index * 35
        rows.append(_plain_icon(68, baseline - 7, PHONE_GLYPH, INK, scale=0.66))
        rows.append(
            '<text x="92" y="%s" font-family="%s" font-weight="700" font-size="22" '
            'fill="%s">%s</text>' % (baseline, font_family, INK, _esc(number))
        )
    if email:
        baseline = 884 + min(len(phones), 3) * 35
        rows.append(_plain_icon(68, baseline - 7, MAIL_GLYPH, INK, scale=0.66))
        rows.append(
            '<text x="92" y="%s" font-family="%s" font-weight="700" font-size="22" '
            'fill="%s">%s</text>' % (baseline, font_family, INK, _esc(email))
        )

    branch_lines = []
    for index, line in enumerate(wrap_branches(branches)):
        branch_lines.append(
            '<text x="1380" y="%s" font-family="%s" font-weight="700" font-size="23" '
            'fill="%s" text-anchor="start" direction="rtl">%s</text>'
            % (945 + index * 34, font_family, INK, _esc(line))
        )

    if logo_src:
        logo = ('<image xlink:href="%s" href="%s" x="165" y="86" width="150" '
                'height="150" preserveAspectRatio="xMidYMid meet"/>'
                % (logo_src, logo_src))
    else:
        logo = ('<circle cx="240" cy="161" r="72" fill="none" stroke="%s" '
                'stroke-width="4"/>' % GOLD)

    if barcode_src:
        barcode = ('<image xlink:href="%s" href="%s" x="664" y="711" width="438" '
                   'height="74" preserveAspectRatio="none"/>'
                   % (barcode_src, barcode_src))
    else:
        barcode = ('<text x="883" y="758" font-family="%s" font-weight="700" '
                   'font-size="27" fill="%s" text-anchor="middle" direction="rtl">%s'
                   '</text>' % (font_family, GOLD_MUTED, _esc(barcode_missing)))

    return """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 1489 1039" preserveAspectRatio="xMidYMid meet">
  <defs>
    <clipPath id="hosnyCardClip">
      <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="{cr}"/>
    </clipPath>
    <clipPath id="hosnyPanelClip"><path d="{panel}"/></clipPath>
    {patterns}
  </defs>

  <rect width="1489" height="1039" fill="{page}"/>
  <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="{cr}" fill="{cream}"/>

  <g clip-path="url(#hosnyCardClip)">
    <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" fill="{cream}"/>
    <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" fill="url(#hosnySoftPattern)"/>

    <!-- left identity sweep -->
    <path d="{panel}" fill="{panel_fill}"/>
    <g clip-path="url(#hosnyPanelClip)">
      <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" fill="url(#hosnyPanelPattern)"/>
    </g>
    <path d="{edge_inner}" fill="none" stroke="#FFF7E7" stroke-width="6"/>
    <path d="{edge}" fill="none" stroke="{gold}" stroke-width="4"/>

    {logo}
    <text x="240" y="394" font-family="{ff}" font-weight="900" font-size="45"
          fill="{ink}" text-anchor="middle" direction="rtl">{brand}</text>
    <text x="240" y="445" font-family="{ff}" font-weight="700" font-size="24"
          fill="{ink}" text-anchor="middle" direction="rtl">{tagline}</text>

    <!-- validity chip -->
    <rect x="58" y="515" width="512" height="116" rx="22" fill="{chip}"
          stroke="{border}" stroke-width="2.4"/>
    {calendar}
    <text x="436" y="553" font-family="{ff}" font-weight="700" font-size="22"
          fill="{ink}" text-anchor="end" direction="rtl">{expiry_label}</text>
    <text x="436" y="598" font-family="{ff}" font-weight="900" font-size="28"
          fill="{ink}" text-anchor="end">{expiry}</text>

    <!-- headline -->
    {cloche}
    <path d="M 736,176 H 884" stroke="{gold}" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M 1004,176 H 1160" stroke="{gold}" stroke-width="2.2" stroke-linecap="round"/>
    <circle cx="916" cy="176" r="4" fill="{gold}"/>
    <circle cx="984" cy="176" r="4" fill="{gold}"/>
    <text x="936" y="316" font-family="{ff}" font-weight="900" font-size="82"
          fill="{ink}" text-anchor="middle" direction="rtl">{headline}</text>
    <text x="936" y="369" font-family="{ff}" font-weight="700" font-size="27"
          fill="{gold_text}" text-anchor="middle" direction="rtl">{subtitle}</text>

    <!-- value cartouche -->
    <path d="{cart}" fill="{brown}" stroke="{gold}" stroke-width="7"/>
    <path d="{cart}" fill="none" stroke="{inner}" stroke-width="2.2"
          transform="translate(904,545) scale(0.956) translate(-904,-545)"/>
    {sprig_l}
    {sprig_r}
    <text x="904" y="467" font-family="{ff}" font-weight="700" font-size="25"
          fill="{gold_bright}" text-anchor="middle" direction="rtl">{value_label}</text>
    <text x="904" y="590" font-family="Georgia, 'Times New Roman', serif"
          font-weight="700" font-size="112" letter-spacing="1.5"
          fill="{gold_bright}" text-anchor="middle">{amount}</text>
    <text x="904" y="638" font-family="{ff}" font-weight="900" font-size="31"
          fill="{gold_bright}" text-anchor="middle" direction="rtl">{currency}</text>

    <!-- barcode and usage hint -->
    <rect x="574" y="696" width="624" height="128" rx="12" fill="#FFFFFF"
          stroke="#E5D8C0" stroke-width="1.5"/>
    {barcode}
    <text x="883" y="811" font-family="{ff}" font-weight="900" font-size="27"
          letter-spacing="1.1" fill="{ink}" text-anchor="middle">{code}</text>
    <path d="M 1238,704 V 814" stroke="{divider}" stroke-width="2"/>
    <text x="1372" y="737" font-family="{ff}" font-weight="900" font-size="27"
          fill="{ink}" text-anchor="start" direction="rtl">{code_title}</text>
    <text x="1372" y="780" font-family="{ff}" font-weight="700" font-size="22"
          fill="{gold_muted}" text-anchor="start" direction="rtl">{hint1}</text>
    <text x="1372" y="812" font-family="{ff}" font-weight="700" font-size="22"
          fill="{gold_muted}" text-anchor="start" direction="rtl">{hint2}</text>

    <!-- footer -->
    <rect x="{cx}" y="{footer_top}" width="{cw}" height="{footer_h}" fill="{panel_fill}"/>
    <rect x="{cx}" y="{footer_top}" width="{cw}" height="{footer_h}" fill="url(#hosnySoftPattern)"/>
    <path d="M {cx},{footer_top} H {card_right}" stroke="{border}" stroke-width="1.5"/>
    {floral}
    {rows}
    {pin}
    <text x="1380" y="902" font-family="{ff}" font-weight="900" font-size="28"
          fill="{ink}" text-anchor="start" direction="rtl">{branches_label}</text>
    {branch_lines}
  </g>

  <rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="{cr}" fill="none"
        stroke="{border}" stroke-width="2"/>
</svg>""".format(
        panel=LEFT_PANEL, edge=LEFT_EDGE, edge_inner=LEFT_EDGE_INNER,
        cart=CARTOUCHE, patterns=_pattern_defs(),
        cx=CARD["x"], cy=CARD["y"], cw=CARD["w"], ch=CARD["h"], cr=CARD["r"],
        card_right=CARD["x"] + CARD["w"],
        footer_top=FOOTER_TOP, footer_h=CARD["y"] + CARD["h"] - FOOTER_TOP,
        floral=_floral("translate(744,974) scale(0.58)", GOLD_ON_FOOTER),
        sprig_l=_sprig("translate(635,545) scale(0.72)"),
        sprig_r=_sprig("translate(1173,545) scale(-0.72,0.72)"),
        calendar=_calendar_icon(518, 574), cloche=_cloche(950, 150),
        pin=_pin_icon(1292, 914, 0.62), rows="\n    ".join(rows),
        branch_lines="\n    ".join(branch_lines),
        logo=logo, barcode=barcode, ff=font_family,
        page=PAGE, cream=CREAM, panel_fill=PANEL, chip=CHIP, border=BORDER,
        ink=INK, brown=BROWN, gold=GOLD, gold_bright=GOLD_BRIGHT,
        gold_text=GOLD_TEXT, gold_muted=GOLD_MUTED,
        inner=GOLD_ON_BROWN, divider=GOLD_ON_CREAM_55,
        brand=_esc(brand), tagline=_esc(tagline), headline=_esc(headline),
        subtitle=_esc(subtitle), value_label=_esc(value_label),
        amount=_esc(amount), currency=_esc(currency), expiry=_esc(expiry),
        expiry_label=_esc(expiry_label), code=_esc(code),
        code_title=_esc(code_title), hint1=_esc(code_hint_1),
        hint2=_esc(code_hint_2), branches_label=_esc(branches_label),
    )
