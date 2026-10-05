# -*- coding: utf-8 -*-
"""
Hosny POS — مراجعة وضبط توجيه طابعات التحضير (preparation printers).

لا يوجد أي ID ثابت في هذا الملف. كل شيء يُحلّ بالاسم مقابل ما هو موجود فعلياً
في قاعدة البيانات، فلو أضفت طابعة أو قسماً أو صنفاً جديداً تعيد تشغيل الأداة
فتضبط الوضع وتخبرك بأي شيء جديد لم يُوجَّه بعد.

  معاينة (لا تكتب شيئاً):
    runuser -u odoo19 -- /opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
      shell -c /etc/odoo19-hosny.conf --no-http --log-level=warn \
      < /opt/Hosney-Pos/tools/pos_printer_routing.py

  تطبيق:  APPLY=1 ... نفس الأمر
"""

import os
import re

APPLY = os.environ.get("APPLY") == "1"
PLACEHOLDER_IP = "0.0.0.0"

# ─── 1) الطابعات المطلوبة: الاسم -> IP (None = جهاز لم يُوصَّل بعد) ────────
PRINTERS = {
    "الشوايه":  "192.168.27.56",
    "المطبخ":   "192.168.27.192",
    "السمك":    "192.168.27.170",
    "الكفتريا": "192.168.27.163",
    "السلطات":  None,   # جهاز جديد — ضع الـ IP عند التوصيل ثم أعد التشغيل
}

# ─── 2) توجيه الأقسام: اسم القسم (بأي لغة) -> اسم الطابعة ────────────────
ROUTING = {
    "الشوايه":  "الشوايه",
    "الأسماك":  "السمك",
    "المطبخ":   "المطبخ",
    "الكفتريا": "الكفتريا",
    "السلطات":  "السلطات",
    "الوجبات":  None,   # توجيه على مستوى الصنف — انظر MEAL_RULES
}

NEVER_PRINT = {"POS MRP Tests", "نقاط البيع"}

# ─── 3) الوجبات المجمّعة: كل وجبة تُضاف لقسم محطتها حسب مكوّنها ──────────
MEAL_CATEGORY = "الوجبات"
MEAL_RULES = [
    (r"سمك|سى فود|سي فود|جمبر",        "الأسماك"),
    (r"كفته|كفتة|مشوى|مشوية|مشاوى",    "الشوايه"),
    (r"مكرونة|بيض|خضار|دجاج|بطاطس",     "المطبخ"),
]
MEAL_DEFAULT = "المطبخ"   # العروض العامة التي لا يظهر مكوّنها من الاسم

# ─── 4) أصناف بلا قسم: كلمة مفتاحية -> القسم ─────────────────────────────
UNCATEGORISED_RULES = [
    (r"مشوي|مشوية|مشاوى|كعبلة|نيفة|مشكل دجاج", "الشوايه"),
    (r"بيبسى|سفن اب|مياه|كانز|ميراندا|عصير",    "الكفتريا"),
]
# لا تُطبع ولا تحتاج قسماً (بطاقات/كوبونات/مواد خام/موقوف)
NO_PRINT_RULES = r"بطاقة الهدايا|كوبونات|خام|متوقف"

SEP = "─" * 74


def raw_names(env, table, ids=None):
    """{id: (كل الأسماء بكل اللغات, الاسم المعروض)} — الأقسام هنا لها اسمان
    عربيان مختلفان حسب اللغة، فالمطابقة على لغة واحدة غير آمنة."""
    q = "SELECT id, name FROM %s" % table
    args = ()
    if ids:
        q += " WHERE id IN %s"
        args = (tuple(ids),)
    env.cr.execute(q, args)
    out = {}
    for rid, name in env.cr.fetchall():
        if isinstance(name, dict):
            vals = {v.strip() for v in name.values() if v}
            display = name.get("ar_001") or name.get("en_US") or ""
        else:
            vals = {(name or "").strip()}
            display = name or ""
        out[rid] = (vals, display.strip())
    return out


def pick(rules, aliases, default=None):
    for pattern, target in rules:
        if any(re.search(pattern, a) for a in aliases):
            return target
    return default


def main(env):
    configs = env["pos.config"].search([("is_order_printer", "=", True)])
    log = []

    # ── الطابعات: أنشئ الناقص ─────────────────────────────────────────
    printers = env["pos.printer"].search([])
    by_name = {p.name.strip(): p for p in printers}
    for pname, ip in PRINTERS.items():
        if pname in by_name:
            continue
        log.append(f"إنشاء طابعة «{pname}»" + ("" if ip else "  (بلا IP بعد)"))
        if APPLY:
            by_name[pname] = env["pos.printer"].create({
                "name": pname,
                "printer_type": "epson_epos",
                "epson_printer_ip": ip or PLACEHOLDER_IP,
            })
    printers = env["pos.printer"].search([])
    by_name = {p.name.strip(): p for p in printers}

    categories = env["pos.category"].search([])
    cat_names = raw_names(env, "pos_category", categories.ids)
    disp = {cid: cat_names[cid][1] for cid in cat_names}
    categ_by_alias = {}
    for c in categories:
        for a in cat_names[c.id][0]:
            categ_by_alias[a] = c

    print(SEP); print("الطابعات على النظام"); print(SEP)
    for p in printers:
        cats = ", ".join(disp[c.id] for c in p.product_categories_ids) or "—"
        ip = p.epson_printer_ip or "—"
        live = ip not in (PLACEHOLDER_IP, "—", "")
        print(f"  [{p.id}] {p.name:<10} {ip:<16} "
              f"{'موصّلة' if live else 'بانتظار التوصيل':<16} أقسامها: {cats}")

    # ── التوجيه المطلوب للأقسام ───────────────────────────────────────
    desired = {p.id: set() for p in printers}
    unknown = []
    for c in categories:
        aliases = cat_names[c.id][0]
        if aliases & NEVER_PRINT:
            continue
        match = [k for k in ROUTING if k in aliases]
        if not match:
            unknown.append(disp[c.id]); continue
        target = ROUTING[match[0]]
        if target is None:
            continue
        p = by_name.get(target)
        if p:
            desired[p.id].add(c.id)
        else:
            print(f"  ✗ الطابعة «{target}» غير موجودة")

    # ── توجيه الأصناف (وجبات مجمّعة + أصناف بلا قسم) ──────────────────
    products = env["product.template"].search([("available_in_pos", "=", True)])
    prod_names = raw_names(env, "product_template", products.ids)
    meal_cat = categ_by_alias.get(MEAL_CATEGORY)
    product_fixes, still_unrouted = [], []

    for t in products:
        aliases, name = prod_names[t.id]
        cur = set(t.pos_categ_ids.ids)

        if not cur:
            if any(re.search(NO_PRINT_RULES, a) for a in aliases):
                continue
            target = pick(UNCATEGORISED_RULES, aliases)
            if target and categ_by_alias.get(target):
                product_fixes.append((t, name, target, categ_by_alias[target].id))
            else:
                still_unrouted.append((name, "بلا قسم"))
            continue

        if meal_cat and meal_cat.id in cur:
            target = pick(MEAL_RULES, aliases, MEAL_DEFAULT)
            tc = categ_by_alias.get(target)
            if tc and tc.id not in cur:
                product_fixes.append((t, name, target, tc.id))

    # ── ماذا يصل لطابعة بعد التطبيق؟ ──────────────────────────────────
    routed = {cid for ids in desired.values() for cid in ids}
    live_routed = {cid for p in printers for cid in desired[p.id]
                   if (p.epson_printer_ip or "") not in (PLACEHOLDER_IP, "")}
    planned = {t.id: cid for t, _, _, cid in product_fixes}
    for t in products:
        aliases, name = prod_names[t.id]
        if any(re.search(NO_PRINT_RULES, a) for a in aliases):
            continue
        cids = set(t.pos_categ_ids.ids) | ({planned[t.id]} if t.id in planned else set())
        if not (cids & routed) and not any(n == name for n, _ in still_unrouted):
            still_unrouted.append((name, ", ".join(disp[i] for i in cids) or "بلا قسم"))

    print(); print(SEP); print("تغييرات التوجيه"); print(SEP)
    for p in printers:
        cur = set(p.product_categories_ids.ids)
        want = desired[p.id]
        if cur != want:
            log.append(f"{p.name}: أقسامها ← {[disp[i] for i in want]}")
            if APPLY:
                p.product_categories_ids = [(6, 0, list(want))]
    for t, name, target, cid in product_fixes:
        log.append(f"صنف «{name}» ← + قسم {target}")
        if APPLY:
            t.pos_categ_ids = [(4, cid)]

    # ── ربط الطابعات بالفروع: فقط الموصّلة فعلياً ─────────────────────
    for p in printers:
        ip = (p.epson_printer_ip or "").strip()
        ready = ip and ip != PLACEHOLDER_IP
        missing = configs - p.pos_config_ids
        if ready and missing:
            log.append(f"{p.name}: ربط بالفروع {[c.name for c in missing]}")
            if APPLY:
                p.pos_config_ids = [(4, c.id) for c in missing]
        elif not ready and p.pos_config_ids:
            log.append(f"{p.name}: فصل عن الفروع حتى يُضبط الـ IP "
                       "(وإلا ظهرت رسالة فشل طباعة على كل طلب)")
            if APPLY:
                p.pos_config_ids = [(5, 0, 0)]

    if not env["ir.config_parameter"].sudo().get_param("point_of_sale.use_lna"):
        log.append("ضبط point_of_sale.use_lna = 1")
        if APPLY:
            env["ir.config_parameter"].sudo().set_param("point_of_sale.use_lna", "1")

    for line in log:
        print("  • " + line)
    if not log:
        print("  لا تغييرات — الإعداد مطابق للمطلوب")

    # ── ما زال بلا طابعة ──────────────────────────────────────────────
    print(); print(SEP); print("تنبيهات"); print(SEP)
    if unknown:
        print(f"  ⚠ أقسام غير معرّفة في ROUTING: {', '.join(unknown)}")
    pend = [p.name for p in printers
            if (p.epson_printer_ip or "") in (PLACEHOLDER_IP, "")]
    if pend:
        print(f"  ⚠ بانتظار توصيل الجهاز: {', '.join(pend)} — "
              "ضع الـ IP في PRINTERS أو من شاشة أودو ثم أعد التشغيل")
    shown = set()
    for name, why in still_unrouted:
        if name not in shown:
            shown.add(name)
            print(f"  ✗ لا يصل لأي طابعة: {name}   ({why})")
    if not unknown and not still_unrouted and not pend:
        print("  ✓ كل صنف معروض في نقاط البيع يصل لمحطة تحضير")

    if APPLY:
        env.cr.commit()
        print("\n  ✓ تم الحفظ — يظهر عند إعادة تحميل شاشة نقاط البيع في كل فرع.")
    else:
        print("\n  [معاينة فقط] للتطبيق: APPLY=1")


main(env)   # noqa: F821  — 'env' يوفّره odoo shell
