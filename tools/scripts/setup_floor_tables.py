# عدد الطاولات في طوابق «أرضي» و«علوي» و«سفري» لكل نقطة بيع مطعم (25 افتراضياً).
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_MODE=check (الافتراضي): يعرض الحالة وما سيُضاف — لا يغيّر شيئاً.
#   HOSNY_MODE=apply : يكمّل كل طابق حتى HOSNY_COUNT طاولة مفعّلة.
#   HOSNY_MODE=undo  : يؤرشف الطاولات الزائدة عن HOSNY_COUNT (الأعلى رقماً)
#                      ما لم يكن عليها طلب مفتوح.
#   HOSNY_COUNT=25   : العدد المطلوب في كل طابق.
#   HOSNY_FLOORS=ground,upper,takeaway : الطوابق المقصودة.
#   HOSNY_CONFIGS=2,3,11 : نقاط بيع محددة بدل كل نقاط بيع المطعم.
#
# الطاولات الجديدة تُرقَّم بعد أكبر رقم في الطابق، وتأخذ مقاس وشكل أغلب طاولاته،
# وتُصفّ تحت آخر صف فيه بنفس المسافات — فلا تتراكب على الطاولات الحالية. الطاولة
# المؤرشفة في نفس الطابق يُعاد تفعيلها قبل إنشاء جديدة. إضافة الطاولات مسموحة
# والوردية مفتوحة (أودو يمنع حذف الطوابق وتعديلها فقط).
import os
import re
from collections import Counter
from statistics import median

MODE = os.environ.get("HOSNY_MODE", "check")
COUNT = int(os.environ.get("HOSNY_COUNT", "25"))
WANTED = [k.strip() for k in os.environ.get("HOSNY_FLOORS", "ground,upper,takeaway").split(",") if k.strip()]
KINDS = {
    "ground": ("أرضي", re.compile(r"أرض|ارض|ground", re.IGNORECASE)),
    "upper": ("علوي", re.compile(r"علو|upper", re.IGNORECASE)),
    "takeaway": ("سفري", re.compile(r"سفري|takeaway|take away|تيك", re.IGNORECASE)),
}

Config = env["pos.config"]
config_ids = [int(x) for x in os.environ.get("HOSNY_CONFIGS", "").split(",") if x.strip()]
configs = Config.browse(config_ids).exists() if config_ids else Config.search([("module_pos_restaurant", "=", True)])
Floor = env["restaurant.floor"].with_context(active_test=False)
Table = env["restaurant.table"].with_context(active_test=False)
Order = env["pos.order"]


def find_floor(config, kind):
    pattern = KINDS[kind][1]
    floors = Floor.search([("pos_config_ids", "in", config.ids), ("active", "=", True)], order="sequence, id")
    return floors.filtered(lambda f: pattern.search(f.name or ""))[:1]


def grid(tables):
    """(x0, next_row_y, dx, dy, cols, template) from the floor's active tables."""
    default = {"shape": "square", "width": 110, "height": 90, "seats": 4}
    if not tables:
        return 90, 80, 130, 120, 5, default
    xs = sorted({round(t.position_h) for t in tables})
    ys = sorted({round(t.position_v) for t in tables})
    gaps_x = [b - a for a, b in zip(xs, xs[1:]) if b - a >= 40]
    gaps_y = [b - a for a, b in zip(ys, ys[1:]) if b - a >= 40]
    common = Counter((t.shape or "square", t.width or 110, t.height or 90, t.seats or 1) for t in tables).most_common(1)[0][0]
    template = {"shape": common[0], "width": common[1], "height": common[2], "seats": common[3]}
    dx = median(gaps_x) if gaps_x else max(template["width"] + 20, 130)
    dy = median(gaps_y) if gaps_y else max(template["height"] + 30, 120)
    cols = max(1, min(len(xs), 8)) if len(xs) > 1 else 5
    return xs[0], ys[-1] + dy, dx, dy, cols, template


def busy_tables(floor):
    return Order.search([("state", "=", "draft"), ("table_id", "in", floor.table_ids.ids)]).table_id


seen = set()
for config in configs:
    print("\n══ %s (id %s)" % (config.name, config.id))
    for kind in WANTED:
        label = KINDS[kind][0]
        floor = find_floor(config, kind)
        if not floor and kind == "takeaway" and MODE == "apply":
            last = max(config.floor_ids.mapped("sequence") or [0])
            floor = Floor.create({"name": label, "sequence": last + 1, "pos_config_ids": [(4, config.id)]})
            print("  «%s»: أُنشئ الطابق (id %s)" % (label, floor.id))
        if not floor:
            print("  «%s»: لا يوجد طابق بهذا الاسم — تخطّي" % label)
            continue
        if floor.id in seen:
            print("  «%s» (id %s): مشترك مع نقطة بيع سابقة — عولج هناك" % (floor.name, floor.id))
            continue
        seen.add(floor.id)

        tables = floor.table_ids
        active = tables.filtered("active").sorted("table_number")
        archived = (tables - active).sorted("table_number")
        numbers = ", ".join(str(n) for n in active.mapped("table_number"))
        print("  «%s» (id %s): %s طاولة مفعّلة [%s]%s" % (
            floor.name, floor.id, len(active), numbers,
            " + %s مؤرشفة" % len(archived) if archived else ""))

        if MODE == "undo":
            extra = active[COUNT:] if len(active) > COUNT else Table.browse()
            keep = extra & busy_tables(floor)
            (extra - keep).write({"active": False})
            print("    أُرشفت %s طاولة%s" % (len(extra - keep), " — بقيت %s عليها طلبات مفتوحة" % len(keep) if keep else ""))
            continue

        need = COUNT - len(active)
        if need <= 0:
            print("    مكتمل (%s ≥ %s)" % (len(active), COUNT))
            continue
        revive = archived[:need]
        x0, y, dx, dy, cols, template = grid(active | revive)
        next_number = max(tables.mapped("table_number") or [0]) + 1
        new_numbers = list(range(next_number, next_number + need - len(revive)))
        print("    سيُعاد تفعيل %s%s، وسيُنشأ %s طاولة: %s" % (
            len(revive), " [%s]" % ", ".join(str(n) for n in revive.mapped("table_number")) if revive else "",
            len(new_numbers), ", ".join(str(n) for n in new_numbers) or "—"))
        if MODE != "apply":
            continue
        revive.write({"active": True})
        for i, number in enumerate(new_numbers):
            Table.create(dict(template, **{
                "floor_id": floor.id,
                "table_number": number,
                "position_h": x0 + (i % cols) * dx,
                "position_v": y + (i // cols) * dy,
            }))
        print("    ✓ المجموع الآن %s" % len(floor.table_ids.filtered("active")))

if MODE == "apply" or MODE == "undo":
    env.cr.commit()
    print("\nتم. افتح نقطة البيع من «متابعة البيع» (أو ?from_backend=True) حتى تظهر الطاولات.")
else:
    print("\nمعاينة فقط — لم يتغير شيء. للتنفيذ: HOSNY_MODE=apply")
