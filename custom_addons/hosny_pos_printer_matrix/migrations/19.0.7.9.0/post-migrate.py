# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """رقم الطلب = رقم الوردية (2026-10-09) للطلبات في الورديات المفتوحة.

    الورديات المغلقة تبقى بأرقامها كما طُبعت وقتها.
    """
    cr.execute("""
        UPDATE pos_order o
           SET tracking_number = o.hosny_session_number::text
          FROM pos_session s
         WHERE o.session_id = s.id
           AND s.state != 'closed'
           AND o.hosny_session_number IS NOT NULL
           AND o.hosny_session_number > 0
    """)
    _logger.info("hosny_pos_printer_matrix %s -> 19.0.7.9.0: %s open-shift orders renumbered",
                 version, cr.rowcount)
