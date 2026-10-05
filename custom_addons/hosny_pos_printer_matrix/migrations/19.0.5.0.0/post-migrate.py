# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """رقم الطلب في الوردية لكل الطلبات الموجودة (طلب 2026-09-27).

    نرقّم طلبات كل جلسة بترتيب إنشائها على الخادم (id)، ثم نضبط عدّاد الجلسة
    على آخر رقم، فتكمل الوردية المفتوحة من حيث وصلت بدل أن تبدأ من 1 من جديد
    ويتكرر رقم فيها.
    """
    cr.execute("""
        UPDATE pos_order o
           SET hosny_session_number = s.rn
          FROM (SELECT id,
                       row_number() OVER (PARTITION BY session_id ORDER BY id) AS rn
                  FROM pos_order
                 WHERE session_id IS NOT NULL) s
         WHERE o.id = s.id
    """)
    orders = cr.rowcount
    cr.execute("""
        UPDATE pos_session ps
           SET hosny_order_counter = c.n
          FROM (SELECT session_id, max(hosny_session_number) AS n
                  FROM pos_order
                 WHERE session_id IS NOT NULL
                 GROUP BY session_id) c
         WHERE ps.id = c.session_id
    """)
    _logger.info(
        "hosny_pos_printer_matrix %s -> 19.0.5.0.0: numbered %s orders across %s sessions",
        version, orders, cr.rowcount)
