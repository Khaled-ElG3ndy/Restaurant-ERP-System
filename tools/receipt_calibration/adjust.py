"""One calibration step: move/scale spec params so our ink boxes land on the FERP ink boxes."""
import copy

BLUR = 1.5   # the photographed thermal print is ~1.5 px fatter than a crisp raster in each dimension


def cy(b):
    return (b[2] + b[3]) / 2


def cx(b):
    return (b[0] + b[1]) / 2


def size_fix(el, o, f, trust_h=True, trust_w=True, damp=0.85, key="size", sx_key="sx"):
    """font-size from the ink height, then scaleX from the remaining width ratio."""
    oh, fh = o[3] - o[2], (f[3] - f[2]) - BLUR
    ow, fw = o[1] - o[0], (f[1] - f[0]) - BLUR
    k = 1.0
    if trust_h and oh > 4:
        k = (fh / oh) ** damp
        el[key] = round(el[key] * k, 2)
    if trust_w and ow > 4:
        sx = el.get(sx_key, 1.0) * (fw / (ow * k))
        el[sx_key] = round(min(1.25, max(0.8, sx)), 3)


def step(spec, found, T):
    s = copy.deepcopy(spec)
    have = lambda *ks: all(k in found and k in T for k in ks)
    err = {k: cy(T[k]) - cy(found[k]) for k in found if k in T}
    errx = {k: cx(T[k]) - cx(found[k]) for k in found if k in T}
    errr = {k: T[k][1] - found[k][1] for k in found if k in T}   # right ink edge

    # ---- sizes & horizontal ----
    simple = {"title": "title", "paid": "status", "address": "address", "simplified": "simplified"}
    for k, sk in simple.items():
        if have(k):
            size_fix(s[sk], found[k], T[k])
            s[sk]["cx"] = round(s[sk]["cx"] + errx[k], 1)
    for k in ("vat", "vat_label"):
        if have(k):
            size_fix(s[k], found[k], T[k])
            s[k]["right"] = round(s[k]["right"] + errr[k], 1)
    labels = [k for k in ("l_invno", "l_type", "l_pay", "l_serial", "l_date", "l_close", "l_note", "l_cust", "l_phone") if have(k)]
    lmap = {"l_invno": "invoice", "l_type": "type", "l_pay": "payment", "l_serial": "serial", "l_date": "date",
            "l_close": "closed", "l_note": "note", "l_cust": "customer", "l_phone": "phone"}
    if labels:
        # one label size for all rows; each fixed label gets its own horizontal scale
        ratios_h = [((T[k][3] - T[k][2]) - BLUR) / (found[k][3] - found[k][2]) for k in labels]
        kh = (sum(ratios_h) / len(ratios_h)) ** 0.85
        s["label"]["size"] = round(s["label"]["size"] * kh, 2)
        for k in labels:
            el = s["rows"][lmap[k]]
            fw, ow = (T[k][1] - T[k][0]) - BLUR, found[k][1] - found[k][0]
            el["lsx"] = round(min(1.3, max(0.75, el.get("lsx", 1.0) * fw / (ow * kh))), 3)
        s["label"]["right"] = round(s["label"]["right"] + sum(errr[k] for k in labels) / len(labels), 1)
    rowkeys = [("invoice", "l_invno", "v_invno"), ("type", "l_type", "v_type"), ("payment", "l_pay", "v_pay"),
               ("serial", "l_serial", "v_serial"), ("date", "l_date", "v_date"), ("closed", "l_close", "v_close"),
               ("note", "l_note", "v_note"), ("customer", "l_cust", "v_cust"), ("phone", "l_phone", "v_phone")]
    for rk, lk, vk in rowkeys:
        el = s["rows"][rk]
        if have(vk):
            size_fix(el, found[vk], T[vk])
            if "cx" in el:
                el["cx"] = round(el["cx"] + errx[vk], 1)
            else:
                el["right"] = round(el["right"] + errr[vk], 1)
    tlabels = [k for k in ("l_net", "l_disc", "l_vat", "l_total") if have(k)]
    tmap = {"l_net": "net", "l_disc": "discount", "l_vat": "tax", "l_total": "total"}
    if tlabels:
        ratios_h = [((T[k][3] - T[k][2]) - BLUR) / (found[k][3] - found[k][2]) for k in tlabels]
        kh = (sum(ratios_h) / len(ratios_h)) ** 0.85
        s["tlabel"]["size"] = round(s["tlabel"]["size"] * kh, 2)
        for k in tlabels:
            el = s["trows"][tmap[k]]
            fw, ow = (T[k][1] - T[k][0]) - BLUR, found[k][1] - found[k][0]
            el["lsx"] = round(min(1.3, max(0.75, el.get("lsx", 1.0) * fw / (ow * kh))), 3)
        s["tlabel"]["right"] = round(s["tlabel"]["right"] + sum(errr[k] for k in tlabels) / len(tlabels), 1)
    for rk, lk, vk in (("net", "l_net", "v_net"), ("discount", "l_disc", "v_disc"), ("tax", "l_vat", "v_vat"), ("total", "l_total", "v_total")):
        el = s["trows"][rk]
        if have(vk):
            size_fix(el, found[vk], T[vk])
            el["right"] = round(el["right"] + errr[vk], 1)
    c = s["cashier"]
    if have("l_cashier"):
        size_fix(c["label"], found["l_cashier"], T["l_cashier"])
        c["label"]["right"] = round(c["label"]["right"] + errr["l_cashier"], 1)
    if False:
        size_fix(c["name"], found["v_cashier"], T["v_cashier"])
        c["name"]["cx"] = round(c["name"]["cx"] + errx["v_cashier"], 1)
    if have("v_printed"):
        # tilted on the FERP slip: width only, and the same height as the meta dates
        size_fix(c["printed"], found["v_printed"], T["v_printed"], trust_h=False)
        c["printed"]["cx"] = round(c["printed"]["cx"] + errx["v_printed"], 1)
    p = s["phone"]
    if have("phone"):
        ow, fw = found["phone"][1] - found["phone"][0], (T["phone"][1] - T["phone"][0]) - BLUR
        k = fw / ow
        p["label"]["size"] = round(p["label"]["size"] * k, 2)
        p["number"]["size"] = round(p["number"]["size"] * k, 2)
        p["cx"] = round(p["cx"] + errx["phone"], 1)
    t = s["table"]
    nums = [k for k in ("r1_unit", "r1_tax", "r1_total", "r2_unit", "r3_unit") if have(k)]
    if nums:
        kh = (sum(((T[k][3] - T[k][2]) - BLUR) / (found[k][3] - found[k][2]) for k in nums) / len(nums)) ** 0.85
        kw = sum(((T[k][1] - T[k][0]) - BLUR) / (found[k][1] - found[k][0]) for k in nums) / len(nums)
        t["num"]["size"] = round(t["num"]["size"] * kh, 2)
        t["num"]["sx"] = round(min(1.25, max(0.8, t["num"].get("sx", 1) * kw / kh)), 3)
    ths = [k for k in ("th_name", "th_qty", "th_tax", "th_total") if have(k)]
    if ths:
        kh = (sum(((T[k][3] - T[k][2]) - BLUR) / (found[k][3] - found[k][2]) for k in ths) / len(ths)) ** 0.85
        kw = sum(((T[k][1] - T[k][0]) - BLUR) / (found[k][1] - found[k][0]) for k in ths) / len(ths)
        t["th"]["size"] = round(t["th"]["size"] * kh, 2)
        t["th"]["sx"] = round(min(1.25, max(0.8, t["th"].get("sx", 1) * kw / kh)), 3)
    names1 = []   # frozen: name size/scale decide where row 1 wraps
    if names1:
        kh = (sum(((T[k][3] - T[k][2]) - BLUR) / (found[k][3] - found[k][2]) for k in names1) / len(names1)) ** 0.85
        kw = sum(((T[k][1] - T[k][0]) - BLUR) / (found[k][1] - found[k][0]) for k in names1) / len(names1)
        t["name"]["size"] = round(t["name"]["size"] * kh, 2)
        t["name"]["sx"] = round(min(1.25, max(0.8, t["name"].get("sx", 1) * kw / kh)), 3)
        t["name"]["pad"] = round(max(0, t["name"]["pad"] - sum(errr[k] for k in names1) / len(names1)), 1)
    if have("r1_total"):
        t["total_pad"] = round(t["total_pad"] - 2 * errx["r1_total"], 1)

    if have("logo"):
        o, f = found["logo"], T["logo"]
        s["logo"]["w"] = round(s["logo"]["w"] * (f[1] - f[0]) / (o[1] - o[0]), 1)
        s["logo"]["h"] = round(s["logo"]["h"] * (f[3] - f[2]) / (o[3] - o[2]), 1)
        s["logo"]["cx"] = round(s["logo"]["cx"] + errx["logo"], 1)
    if have("qr"):
        o, f = found["qr"], T["qr"]
        s["qr"]["size"] = round(s["qr"]["size"] * ((f[1] - f[0]) + (f[3] - f[2])) / ((o[1] - o[0]) + (o[3] - o[2])), 1)
        s["qr"]["cx"] = round(s["qr"]["cx"] + errx["qr"], 1)

    # ---- vertical chain (cumulative): each anchor's param absorbs its error minus what the previous anchor moved ----
    prev = 0.0
    def chain(errk, holder, key):
        nonlocal prev
        if errk in err:
            holder[key] = round(holder[key] + err[errk] - prev, 1)
            prev = err[errk]
    chain("logo", s["logo"], "mt")
    chain("title", s["title"], "mt")
    chain("paid", s["status"], "mt")
    if have("vat"):
        # the row follows the VAT number; the label moves inside the row
        s["vatrow"]["mt"] = round(s["vatrow"]["mt"] + err["vat"] - prev, 1)
        if have("vat_label"):
            s["vat_label"]["top"] = round(s["vat_label"]["top"] + err["vat_label"] - err["vat"], 1)
        prev = err["vat"]
    chain("address", s["address"], "mt")
    chain("simplified", s["simplified"], "mt")
    first = True
    last_holder = None
    for rk, lk, vk in rowkeys:
        el = s["rows"][rk]
        if lk not in err:
            continue
        if first:
            s["meta"]["mt"] = round(s["meta"]["mt"] + err[lk] - prev, 1)
            first = False
        else:
            last_holder["h"] = round(last_holder["h"] + err[lk] - prev, 1)
        prev = err[lk]
        if vk in err:
            el["vt"] = round(el["vt"] + err[vk] - err[lk], 1)
        last_holder = el
    if "th_name" in err and last_holder is not None:
        last_holder["h"] = round(last_holder["h"] + err["th_name"] - prev, 1)
        prev = err["th_name"]
    ref = "r6_name" if "r6_name" in err else None
    if ref:
        prev = err[ref]
    first = True
    for rk, lk, vk in (("net", "l_net", "v_net"), ("discount", "l_disc", "v_disc"), ("tax", "l_vat", "v_vat"), ("total", "l_total", "v_total")):
        el = s["trows"][rk]
        if lk not in err:
            continue
        if first:
            s["totals"]["mt"] = round(s["totals"]["mt"] + err[lk] - prev, 1)
            first = False
        else:
            last_holder["h"] = round(last_holder["h"] + err[lk] - prev, 1)
        prev = err[lk]
        if vk in err:
            el["vt"] = round(el["vt"] + err[vk] - err[lk], 1)
        last_holder = el
    if False and "v_cashier" in err:
        last_holder["h"] = round(last_holder["h"] + err["v_cashier"] - prev, 1)
        prev = err["v_cashier"]
        if "l_cashier" in err:
            c["label"]["top"] = round(c["label"]["top"] + err["l_cashier"] - err["v_cashier"], 1)
    if False and "v_printed" in err:
        c["name"]["lh"] = round(c["name"]["lh"] + err["v_printed"] - prev, 1)
        prev = err["v_printed"]
    # footer below the totals is tuned by hand (the FERP slip is bent there)
    return s
