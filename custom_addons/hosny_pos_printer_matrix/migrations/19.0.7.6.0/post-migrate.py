# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """فاتورة مجمّعة للسفري في الشواية (طلب 2026-10-04).

    طلب السفري يتجمّع في قسم الشواية: كل محطة تطبع أصنافها كما هي، والشواية
    تطبع فوق تذكرتها «فاتورة مجمعة» بكل أصناف الطلب من كل الأقسام حتى يجمع
    الكنترول الطلب. نفعّل Bundeled Receipt على سطر (الشوايه × سفري) فقط؛ يبقى
    قابلاً للتعديل من شاشة الطابعة.
    """
    cr.execute(
        """
        UPDATE pos_printer_line l
           SET bundled = TRUE,
               bundled_copies = GREATEST(COALESCE(l.bundled_copies, 0), 1),
               bundled_report = COALESCE(l.bundled_report, 'ferp')
          FROM pos_printer p, pos_order_type t
         WHERE p.id = l.printer_id
           AND t.id = l.order_type_id
           AND t.code = 'safari'
           AND (p.name LIKE '%%الشوايه%%' OR p.name LIKE '%%الشواية%%')
     RETURNING l.id, p.name
        """
    )
    rows = cr.fetchall()
    if not rows:
        _logger.warning("hosny_pos_printer_matrix 19.0.7.6.0: no grill × safari printer line found, nothing enabled")
    for line_id, name in rows:
        _logger.info("hosny_pos_printer_matrix 19.0.7.6.0: bundled receipt enabled on line %s (%s × safari)", line_id, name)
