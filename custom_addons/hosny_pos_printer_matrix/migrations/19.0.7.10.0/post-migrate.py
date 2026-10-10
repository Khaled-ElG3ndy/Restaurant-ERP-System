# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """السفري المفتوح يظهر برقم الوردية لا برقم الجهاز (2026-10-10).

    الاسم العائم الآلي (أرقام فقط أو مرجع الطلب) في الورديات المفتوحة يصير رقم
    الوردية. الأسماء المكتوبة يدوياً والورديات المغلقة لا تتغير.
    """
    cr.execute("""
        UPDATE pos_order o
           SET floating_order_name = o.hosny_session_number::text
          FROM pos_session s
         WHERE o.session_id = s.id
           AND s.state != 'closed'
           AND o.hosny_session_number > 0
           AND (o.floating_order_name ~ '^[0-9]+$' OR o.floating_order_name = o.pos_reference)
           AND o.floating_order_name IS DISTINCT FROM o.hosny_session_number::text
    """)
    _logger.info("hosny_pos_printer_matrix %s -> 19.0.7.10.0: %s open takeaway names renumbered",
                 version, cr.rowcount)
