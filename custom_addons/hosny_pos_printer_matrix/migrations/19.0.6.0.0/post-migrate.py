# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# نفس الأسماء التي كانت pos_entry_selector تتعرّف بها على «طابق السفري».
TAKEAWAY_FLOOR_PATTERN = "(سفري|takeaway|take away|تيك)"


def migrate(cr, version):
    """السفري بلا طاولة (طلب 2026-09-27).

    قبل هذه النسخة كانت بطاقة «سفري» تُجلس الطلب على طاولة في طابق اسمه «سفري»
    ولا تسجّل نوعه، فكل الطلبات order_type_id = NULL وتُطبع «محلي». هنا:

    1. الطلبات على طاولات طابق السفري ← سفري، وعلى أي طاولة أخرى ← محلي.
       الطلبات القديمة بلا طاولة تبقى بلا نوع: بينها قسمة طاولة «3B» وطلب
       تطبيق توصيل، ولا يصح تخمين نوعها.
    2. المرتجع يأخذ نوع طلبه الأصلي.
    3. طلبات السفري المفتوحة (draft) تُفصل عن الطاولة، كما سيُنشأ أي سفري
       جديد، وتأخذ اسماً عائماً (رقم التتبّع) كما يفعل أودو لأي طلب بلا طاولة.
       المغلقة والملغاة تحتفظ بطاولتها كما حدثت: لا نعيد كتابة التاريخ.
    """
    cr.execute("SELECT id FROM pos_order_type WHERE code = 'safari' ORDER BY company_id NULLS LAST, id LIMIT 1")
    takeaway = cr.fetchone()
    cr.execute("SELECT id FROM pos_order_type WHERE code = 'local' ORDER BY company_id NULLS LAST, id LIMIT 1")
    local = cr.fetchone()
    if not takeaway or not local:
        _logger.warning("hosny_pos_printer_matrix 19.0.6.0.0: order types 'safari'/'local' missing, nothing migrated")
        return

    cr.execute("""
        UPDATE pos_order o
           SET order_type_id = CASE WHEN f.name ~* %s THEN %s ELSE %s END
          FROM restaurant_table t
          JOIN restaurant_floor f ON f.id = t.floor_id
         WHERE t.id = o.table_id
           AND o.order_type_id IS NULL
     RETURNING o.order_type_id
    """, [TAKEAWAY_FLOOR_PATTERN, takeaway[0], local[0]])
    typed = [row[0] for row in cr.fetchall()]

    cr.execute("""
        UPDATE pos_order r
           SET order_type_id = src.order_type_id
          FROM (SELECT DISTINCT ON (rl.order_id) rl.order_id, o.order_type_id
                  FROM pos_order_line rl
                  JOIN pos_order_line ol ON ol.id = rl.refunded_orderline_id
                  JOIN pos_order o ON o.id = ol.order_id
                 WHERE o.order_type_id IS NOT NULL
                 ORDER BY rl.order_id, rl.id) src
         WHERE r.id = src.order_id
           AND r.is_refund
           AND r.order_type_id IS DISTINCT FROM src.order_type_id
    """)
    refunds = cr.rowcount

    cr.execute("""
        UPDATE pos_order o
           SET table_id = NULL,
               floating_order_name = COALESCE(NULLIF(o.floating_order_name, ''),
                                              NULLIF(o.tracking_number, ''), o.pos_reference)
          FROM pos_order_type ot
         WHERE ot.id = o.order_type_id
           AND ot.code IN ('safari', 'takeaway', 'delivery')
           AND o.state = 'draft'
           AND o.table_id IS NOT NULL
     RETURNING o.id
    """)
    unseated = [row[0] for row in cr.fetchall()]

    cr.execute("SELECT count(*) FROM pos_order WHERE order_type_id IS NULL")
    untyped = cr.fetchone()[0]
    _logger.info(
        "hosny_pos_printer_matrix %s -> 19.0.6.0.0: typed %s orders (%s takeaway, %s local), "
        "%s refunds took their order's type, open takeaway orders taken off their table: %s, "
        "left untyped (no table): %s",
        version, len(typed), typed.count(takeaway[0]), typed.count(local[0]),
        refunds, unseated, untyped)
