# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """كل طابعات المطبخ تطبع بتصميم FERP («نسخة المطبخ») — طلب 2026-09-26.

    القالب القياسي والمختصر يبقيان خياراً في شاشة الطابعة لمن أراد الرجوع
    لطابعة بعينها دون نشر جديد.
    """
    cr.execute(
        "UPDATE pos_printer_line SET report_template = 'ferp' "
        "WHERE report_template IS DISTINCT FROM 'ferp'")
    main = cr.rowcount
    cr.execute(
        "UPDATE pos_printer_line SET bundled_report = 'ferp' "
        "WHERE bundled_report IS DISTINCT FROM 'ferp'")
    _logger.info(
        "hosny_pos_printer_matrix %s -> 19.0.4.0.0: %s printer lines and %s "
        "bundled reports switched to the FERP kitchen ticket",
        version, main, cr.rowcount)
