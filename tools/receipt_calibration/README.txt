معايرة فاتورة العميل (تصميم FERP) — hosny_pos_receipt/static/src/css/ferp_receipt.css ملف مولَّد من هنا.

ferp/            صورة FERP، تصحيح المنظور (edges.py → rectify.py → rect.png/norm.png)،
                 صناديق الحبر لكل عنصر بإحداثيات الطباعة (ferp_canvas.json, ferp_table.json).
                 التحويل: canvas = (rect - (10, -2.2)) × 576/586 — الجدول يملأ عرض الطباعة 576 نقطة.
spec.json        كل المقاسات (خط، حجم، scaleX، موضع) — المصدر الوحيد للـ CSS.
ferp_css.py      يولّد الـ CSS من spec.json:  python ferp_css.py > ../../addons/hosny_pos_receipt/static/src/css/ferp_receipt.css
calibrate.py     يرسم الفاتورة ببيانات FERP داخل نقاط البيع نفسها (htmlToCanvas) ويقارن حبر كل عنصر بـ FERP.
                 calibrate.py 1 --no-adjust          قياس فقط (CSS من spec.json يُحقن في الصفحة)
                 calibrate.py 1 --no-adjust --bundle  قياس بالـ CSS الموجود في الحزمة فعلاً
                 calibrate.py N                       N دورات ضبط تلقائي (adjust.py) — الجزء تحت «الإجمالي» يُضبط يدوياً
e2e/receipt_e2e.py  اختبار كامل على نسخة المراجعة (26 فحصاً): سفري → «طباعة» → دفع أجل → طباعة الإيصال → طاولة.
                 يحتاج نسخة مراجعة على 18105 (/tmp/hosny-receipt-work) و playwright.
