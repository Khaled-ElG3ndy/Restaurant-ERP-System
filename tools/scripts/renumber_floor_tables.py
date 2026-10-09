# إعادة ترقيم طاولات طابق: «علوي» 1…25 ← 101…125 (افتراضياً).
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_MODE=check (الافتراضي): يعرض الترقيم القديم والجديد — لا يغيّر شيئاً.
#   HOSNY_MODE=apply : يطبّق الترقيم.
#   HOSNY_FLOOR=upper : الطابق (ground / upper / takeaway).
#   HOSNY_START=101   : رقم أول طاولة؛ الباقي بالترتيب الحالي.
#   HOSNY_CONFIGS=2   : نقطة البيع التي يُبحث فيها عن الطابق (الطابق مشترك بين
#                       الفروع، فيكفي أي واحدة؛ الافتراضي أول نقطة بيع مطعم).
#
# الطلبات مربوطة بالطاولة نفسها لا برقمها، فالطلبات المفتوحة تبقى عليها وتظهر
# بالرقم الجديد. التذاكر المطبوعة قبل التغيير تبقى بالرقم القديم.
import os
import re

MODE = os.environ.get("HOSNY_MODE", "check")
KIND = os.environ.get("HOSNY_FLOOR", "upper")
START = int(os.environ.get("HOSNY_START", "101"))
PATTERNS = {
    "ground": re.compile(r"أرض|ارض|ground", re.IGNORECASE),
    "upper": re.compile(r"علو|upper", re.IGNORECASE),
    "takeaway": re.compile(r"سفري|takeaway|take away|تيك", re.IGNORECASE),
}

Config = env["pos.config"]
config_ids = [int(x) for x in os.environ.get("HOSNY_CONFIGS", "").split(",") if x.strip()]
configs = Config.browse(config_ids).exists() if config_ids else Config.search([("module_pos_restaurant", "=", True)])
Floor = env["restaurant.floor"].with_context(active_test=False)

floor = Floor.browse()
for config in configs:
    floor = Floor.search([("pos_config_ids", "in", config.ids), ("active", "=", True)], order="sequence, id").filtered(
        lambda f: PATTERNS[KIND].search(f.name or "")
    )[:1]
    if floor:
        break

if not floor:
    print("لا يوجد طابق من نوع %s — لم يتغير شيء." % KIND)
else:
    tables = floor.table_ids
    active = tables.filtered("active").sorted(lambda t: (t.table_number, t.id))
    archived = tables - active
    plan = [(t, START + i) for i, t in enumerate(active)]
    new_numbers = {n for _, n in plan}
    clash = archived.filtered(lambda t: t.table_number in new_numbers)
    busy = env["pos.order"].search([("state", "=", "draft"), ("table_id", "in", active.ids)]).table_id

    print("«%s» (id %s) — نقاط البيع: %s" % (floor.name, floor.id, "، ".join(floor.pos_config_ids.mapped("name"))))
    print("  %s طاولة مفعّلة: %s ← %s" % (
        len(active),
        "%s…%s" % (active[:1].table_number, active[-1:].table_number) if active else "—",
        "%s…%s" % (START, START + len(active) - 1) if active else "—"))
    for table, number in plan:
        if table.table_number != number:
            print("    %s ← %s%s" % (table.table_number, number, "  (عليها طلب مفتوح)" if table in busy else ""))
    if clash:
        print("  تنبيه: طاولات مؤرشفة بنفس الأرقام الجديدة: %s — ستُنقل لأرقام سالبة حتى لا تتكرر"
              % ", ".join(str(n) for n in clash.mapped("table_number")))

    if MODE == "apply":
        for table in clash:
            table.table_number = -table.id
        for table, number in plan:
            if table.table_number != number:
                table.table_number = number
        env.cr.commit()
        print("\nتم. افتح نقطة البيع من «متابعة البيع» (أو ?from_backend=True) حتى تظهر الأرقام الجديدة.")
    else:
        print("\nمعاينة فقط — لم يتغير شيء. للتنفيذ: HOSNY_MODE=apply")
