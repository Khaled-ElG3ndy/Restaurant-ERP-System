# نشر hosny_pos_printer_matrix على الإنتاج

## الحالة

| النسخة | المحتوى | على الإنتاج؟ |
|---|---|---|
| 19.0.1.0.0 | أنواع الفواتير + عدد النسخ + القالب + Bundeled + Is Chief | ✅ منشورة 2026-09-15 |
| 19.0.2.0.0 | + تبويب مجموعات الوجبات + تبويب الأصناف + الاستثناءات | ✅ منشورة 2026-09-15 |
| 19.0.2.3.0 | شبكة خلايا بإطار بنفس شكل FERP (الاسم جهة والمربّع جهة) | ✅ منشورة |
| 19.0.2.4.0 | **٣ أعمدة ثابتة** (٢ على التابلت، ١ على الموبايل) | ❌ مُختبرة على نسخة المراجعة فقط |
| 19.0.4.0.0 | تذكرة المطبخ بتصميم FERP «نسخة المطبخ» + Cashier (من ضرب الفاتورة) — قالب `ferp` افتراضي، والترحيل يحوّل كل الأسطر إليه | ✅ منشورة 2026-09-27 09:58 UTC |
| 19.0.5.0.0 | «رقم الفاتورة» على تذكرة المطبخ = رقم الطلب في الوردية (1، 2، 3…) بدل رقم التتبّع ذي الخمس خانات | 2026-09-27 |
| 19.0.6.0.0 | السفري بلا طاولة: نوع الفاتورة يُسجَّل على كل طلب، والسفري لا يُجلس على طاولة ولا يرجع لخريطة الطاولات (مع pos_entry_selector 19.0.1.2.0) | 2026-09-27 |

### 19.0.6.0.0 — السفري بلا طاولة

**السبب:** بطاقة «سفري» كانت تُجلس الطلب على أول طاولة فارغة في طابق اسمه «سفري» ولا
تسجّل نوعه، والشاشة ترسل `order_type_id = false` فلا يعمل الافتراضي على الخادم: كل
الطلبات NULL وتُطبع «محلي». ولأن الطلب على طاولة، يرجع أودو بعد «إرسال الطلب» وبعد
الدفع لخريطة الطاولات.

- **القاعدة (شاشة + خادم):** النوع هو المرجع والطاولة تتبعه. `safari` / `takeaway` /
  `delivery` بلا طاولة دائماً؛ أي نوع آخر (محلي) على طاولة. طلب جديد بلا نوع: على
  طاولة ← محلي، بدون طاولة ← سفري (لا يُعتبر طلب بلا طاولة محلياً أبداً). المرتجع
  يأخذ نوع طلبه الأصلي. نقطة بيع قديمة ترسل `false` لا تمسح نوعاً مسجّلاً.
- **الشاشة:** «سفري» يفتح طلب سفري بلا طاولة؛ بعد «إرسال الطلب» يبقى على الشاشة، وبعد
  الدفع يفتح سفري جديد. شارة «سفري / محلي · الطاولة» بجانب «اختر المكان» تبدّل النوع:
  سفري يُفرغ الطاولة، ومحلي يفتح اختيار الطاولة (مثل «تحويل») ولا يصير محلياً إلا بها.
  طابق «سفري» يختفي من أزرار الطوابق ما دام لا طلب مفتوح عليه. طلبات السفري غير
  المدفوعة في «تسديد الفواتير».
- **الترحيل** `migrations/19.0.6.0.0/post-migrate.py`: الطلبات على طاولات طابق السفري ←
  سفري، وعلى باقي الطاولات ← محلي؛ طلبات السفري المفتوحة تُفصل عن الطاولة (المغلقة
  تحتفظ بطاولتها). الطلبات القديمة بلا طاولة تبقى بلا نوع. لا أعمدة جديدة.
- **الترقية:** نفس الأوامر بالأسفل لكن `-u hosny_pos_printer_matrix,pos_entry_selector` (الاثنان معاً)،
  وانسخ `pos_entry_selector` إلى `/opt/Hosney-Pos/addons/` مع هذا الموديول.
- **بعد النشر:** أعد تحميل نقطة البيع في كل فرع (F5). الشاشة القديمة تبقى تعمل بالطريقة
  القديمة حتى تُحمَّل من جديد.
- **الاختبارات:** `tests/test_order_type_table.py` (18 اختبار على `sync_from_ui`).

### 19.0.5.0.0 — رقم الطلب في الوردية

- حقل `pos.order.hosny_session_number` + عدّاد `pos.session.hosny_order_counter`. الخادم وحده يعطي
  الرقم عند إنشاء الطلب (UPDATE … RETURNING على صف الجلسة: جهازان في نفس اللحظة لا يأخذان نفس الرقم)،
  ويتجاهل أي قيمة ترسلها الشاشة. طلب مفتوح ينتقل لوردية جديدة يأخذ رقماً منها.
- الشاشة: لو الطلب بلا رقم عند «إرسال الطلب» تزامنه أولاً ثم تطبع (أودو يطبع الطلب الجديد قبل أول
  مزامنة). لو فشلت المزامنة تُطبع التذكرة برقم التتبّع كما كانت.
- `migrations/19.0.5.0.0/post-migrate.py` يرقّم الطلبات الموجودة في كل جلسة بترتيب إنشائها ويضبط
  العدّاد، فالوردية المفتوحة تكمل من حيث وصلت.
- **تحذير:** الإصدار يضيف أعمدة. لا تترك ملفاته في custom_addons بدون ترقية: أي إعادة تشغيل عادية
  ستحمّل كوداً أعمدته غير موجودة وتسقط نقاط البيع. انسخ ورقّ في نفس الخطوة.

### 19.0.4.0.0 — تذكرة المطبخ بتصميم FERP

- القالب `hosny_pos_printer_matrix.KitchenTicket` (static/src/xml/kitchen_ticket.xml)، الستايل
  static/src/css/kitchen_ticket.css، والخطوط المضمّنة في static/fonts (Amiri / Noto Naskh Arabic /
  Wine Tahoma / Liberation Serif — تراخيصها بجانبها).
- `migrations/19.0.4.0.0/post-migrate.py` يحوّل `report_template` و `bundled_report` لكل الأسطر إلى `ferp`.
- **رجوع سريع بدون نشر:** من شاشة الطابعة اختر «التذكرة القياسية» في «اسم التقرير» للطابعة/النوع
  المطلوب، ثم أعد تحميل نقاط البيع في الفرع.
- الأحجام معايَرة على مسار الطباعة الحقيقي: html-to-image يكتب font-size = floor(x) − 0.1، والـ POS
  كله `text-rendering: geometricPrecision`، و hosny_pos_theme يفرض Cairo على `.pos *` بـ !important
  (لذلك كل font-family في التذكرة !important). لا تعاير الأحجام من معاينة صفحة عادية.

## ترقية الإنتاج (نفس الأوامر لأي نسخة)

نفس تسلسل النشر بالأسفل مع `-u` بدل `-i`:

```bash
sudo -u postgres pg_dump -Fc hosny > /opt/Hosney-Pos/tools/backups/hosny-$(date +%F-%H%M).dump
systemctl stop odoo19-hosny.service
sudo -u postgres psql -d hosny -c \
  "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%' AND name LIKE '%point_of_sale%';"
runuser -u odoo19 -- /opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
  -c /etc/odoo19-hosny.conf -u hosny_pos_printer_matrix --stop-after-init
systemctl start odoo19-hosny.service
rm -rf /var/cache/nginx/odoo_hosny/* && systemctl reload nginx
```

تحقق بعدها من إنشاء جدولي الربط الجديدين:

```bash
sudo -u postgres psql -d hosny -tAc \
  "select count(*) from information_schema.tables
   where table_name in ('pos_printer_product_rel','pos_printer_product_excl_rel');"
# المتوقع: 2
```

---

## النشر الأول (مرجع)

الأوامر التالية هي خطوة النشر — تحتاج موافقتك لأنها توقف الخدمة
وتعيد تشغيل نقاط البيع في الفروع الثلاثة.

## قبل التنفيذ

تأكد أن لا وردية مفتوحة عليها طلبات جارية:

```bash
sudo -u postgres psql -d hosny -tAc \
  "select config_id, state from pos_session where state='opened';"
```

خذ نسخة احتياطية:

```bash
sudo -u postgres pg_dump -Fc hosny > /opt/Hosney-Pos/tools/backups/hosny-$(date +%F-%H%M).dump
```

## النشر (٥ خطوات بالترتيب)

```bash
# 1) إيقاف الخدمة
systemctl stop odoo19-hosny.service

# 2) إسقاط حزم أصول نقاط البيع المخزّنة
sudo -u postgres psql -d hosny -c \
  "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%' AND name LIKE '%point_of_sale%';"

# 3) تثبيت الموديول (تثبيت جديد، وليس ترقية)
runuser -u odoo19 -- /opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
  -c /etc/odoo19-hosny.conf -i hosny_pos_printer_matrix --stop-after-init

# 4) تشغيل الخدمة
systemctl start odoo19-hosny.service

# 5) تفريغ كاش nginx
rm -rf /var/cache/nginx/odoo_hosny/* && systemctl reload nginx
```

## التحقق بعد النشر

```bash
# أنواع الفواتير الأربعة + ٢٠ سطر مصفوفة (٥ طابعات × ٤ أنواع)
sudo -u postgres psql -d hosny -tAc \
  "select (select count(*) from pos_order_type) types,
          (select count(*) from pos_printer_line) lines;"
```

ثم من المتصفح في الفرع: افتح نقاط البيع، يظهر زر «نوع الفاتورة» بجانب أزرار
التحكم. الطباعة نفسها تُختبر من الفرع فقط — السيرفر لا يصل لشبكة الفروع.

## التراجع

```bash
systemctl stop odoo19-hosny.service
echo "env['ir.module.module'].search([('name','=','hosny_pos_printer_matrix')]).button_immediate_uninstall(); env.cr.commit()" \
 | runuser -u odoo19 -- /opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
   shell -c /etc/odoo19-hosny.conf --no-http
systemctl start odoo19-hosny.service
rm -rf /var/cache/nginx/odoo_hosny/* && systemctl reload nginx
```

إلغاء التثبيت مُجرَّب فعلياً على نسخة المراجعة ونجح.

## نسخة المراجعة

تعمل الآن على `127.0.0.1:18094` (قاعدة `hosny_prtest`, عمال=0, بلا cron,
بريد معطّل). للوصول من جهازك:

```bash
ssh -L 18094:127.0.0.1:18094 <هذا-السيرفر>
# ثم http://127.0.0.1:18094
```

لإيقافها وحذفها بعد الانتهاء:

```bash
pkill -f "hosny-prtest/odoo.conf"
sudo -u postgres dropdb hosny_prtest
rm -rf /opt/hosny-prtest
```
