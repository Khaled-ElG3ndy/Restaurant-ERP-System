# طاولات «سفري 1…15» لطلبات الهاتف: طابق «سفري» لكل نقطة بيع مطعم.
#
# يُشغَّل داخل odoo-bin shell (المتغير env موجود هناك).
#   HOSNY_MODE=apply (الافتراضي): ينشئ الطابق والطاولات الناقصة (لا يكرر شيئاً).
#   HOSNY_MODE=undo : يؤرشف طاولات «سفري» التي ليس عليها طلب مفتوح.
#   HOSNY_CONFIGS=2,3 : نقاط بيع محددة بدل كل نقاط بيع المطعم.
#
# اسم الطابق «سفري» بالضبط: به يعرفه pos_entry_selector (التبويب واللون الوردي)
# و hosny_pos_printer_matrix (الطلب على طاولته سفري ويحتفظ بها).
import os
import re

MODE = os.environ.get("HOSNY_MODE", "apply")
COUNT = 15
FLOOR_NAME = "سفري"
TAKEAWAY_FLOOR_RE = re.compile(r"سفري|takeaway|take away|تيك", re.IGNORECASE)

Config = env["pos.config"]
config_ids = [int(x) for x in os.environ.get("HOSNY_CONFIGS", "").split(",") if x.strip()]
configs = Config.browse(config_ids).exists() if config_ids else Config.search([("module_pos_restaurant", "=", True)])
Floor = env["restaurant.floor"].with_context(active_test=False)
Table = env["restaurant.table"].with_context(active_test=False)


def takeaway_floors(config, active_only=True):
    floors = Floor.search([("pos_config_ids", "in", config.ids)])
    return floors.filtered(lambda f: TAKEAWAY_FLOOR_RE.search(f.name or "") and (f.active or not active_only))


if MODE == "undo":
    for config in configs:
        for floor in takeaway_floors(config):
            busy = env["pos.order"].search([("state", "=", "draft"), ("table_id", "in", floor.table_ids.ids)]).table_id
            free = floor.table_ids.filtered(lambda t: t.active) - busy
            free.write({"active": False})
            print("%s: أُرشفت %s طاولة من «%s»%s" % (
                config.name, len(free), floor.name,
                " — بقيت %s عليها طلبات مفتوحة" % len(busy) if busy else ""))
    env.cr.commit()
else:
    for config in configs:
        floor = takeaway_floors(config)[:1]
        if not floor:
            # إنشاء طابق جديد مسموح والوردية مفتوحة (تعديل طابق قائم غير مسموح)
            last = max(config.floor_ids.mapped("sequence") or [0])
            floor = Floor.create({"name": FLOOR_NAME, "sequence": last + 1, "pos_config_ids": [(4, config.id)]})
            created_floor = True
        else:
            created_floor = False
        existing = {t.table_number: t for t in floor.table_ids}
        added = reactivated = 0
        for n in range(1, COUNT + 1):
            i = n - 1
            table = existing.get(n)
            if table and not table.active:
                table.active = True
                reactivated += 1
            elif not table:
                Table.create({
                    "floor_id": floor.id,
                    "table_number": n,
                    "shape": "square",
                    "seats": 1,
                    "width": 110,
                    "height": 90,
                    "position_h": 90 + (i % 5) * 130,
                    "position_v": 80 + (i // 5) * 120,
                })
                added += 1
        print("%s: طابق «%s» (id %s)%s — أُضيفت %s طاولة، وأُعيد تفعيل %s، والمجموع الآن %s" % (
            config.name, floor.name, floor.id, " جديد" if created_floor else "",
            added, reactivated, len(floor.table_ids.filtered("active"))))
    env.cr.commit()
    print("\nافتح نقطة البيع من لوحة أودو («متابعة البيع») حتى يحمّل المتصفح الطابق الجديد.")
