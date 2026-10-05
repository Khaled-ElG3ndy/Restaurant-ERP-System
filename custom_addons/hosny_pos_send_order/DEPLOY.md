# نشر hosny_pos_send_order 19.0.2.0.0 + hosny_pos_printer_matrix 19.0.3.0.0

إصلاحان يُنشران معاً:

1. **زر «إرسال الطلب»** — كان يرمي TypeError قبل أن يفعل أي شيء، ولم يكن
   يستدعي `super` فيتخطّى خط الطباعة كله. الشرح في رأس
   `hosny_pos_send_order/static/src/app/store/order_send_state.js`.
2. **طباعة ePOS كانت مكسورة بالكامل** — الموديول القديم `pos_epson_printer`
   (بقية أودو 17) يعمل patch على `createPrinter` ويرجّع كلاس v17 يستورد
   `templates` من `@web/core/assets`، وهو غير مُصدَّر في أودو 19، فينفجر في كل
   طباعة تذكرة تحضير. الشرح في
   `hosny_pos_printer_matrix/data/ir_asset_data.xml`.

   ملاحظة: فاتورة الكاشير لم تكن متأثرة لأن أودو يبني طابعة الفاتورة مباشرة من
   الكلاس الأساسي (`pos_store.js:730`) ولا تمرّ على `createPrinter` — لذلك كانت
   الفواتير تُطبع وتذاكر المطبخ لا.

نسخة ما قبل الإصلاح:
`/opt/Hosney-Pos/tools/backups/hosny_pos_send_order-2026-09-23-pre-fix`

## قبل النشر

النشر يعيد تشغيل الخدمة، أي أنه **يعيد تحميل نقاط البيع في الفروع الثلاثة**.
اختر نافذة هادئة، وتحقق من النشاط أولاً:

```bash
sudo -u postgres psql -d hosny -tAc \
  "select max(date_order) from pos_order;"
sudo -u postgres psql -d hosny -tAc \
  "select id, config_id, state from pos_session where state != 'closed';"
```

الطلبات المفتوحة محفوظة في قاعدة البيانات وتنجو من إعادة التشغيل.

## النشر

تعديل الملفات على القرص **لا يفعل شيئاً** وحده: أودو يعمل بدون dev mode،
فحزمة الأصول لا تُبنى إلا عند ترقية موديول. الخطوات الست كلها، بالترتيب:

```bash
sudo -u postgres psql -d hosny -c \
  "\copy (select * from pos_order) to '/opt/Hosney-Pos/tools/backups/pos_order-$(date +%F-%H%M).csv' csv header"

systemctl stop odoo19-hosny.service

psql -h 127.0.0.1 -U odoo19 -d hosny -c \
  "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%' AND name LIKE '%point_of_sale%';"

runuser -u odoo19 -- /opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
  -c /etc/odoo19-hosny.conf -u hosny_pos_send_order,hosny_pos_printer_matrix --stop-after-init

systemctl start odoo19-hosny.service

rm -rf /var/cache/nginx/odoo_hosny/* && systemctl reload nginx
```

الموديولان يُرقَّيان في أمر واحد. لا تُلغِ تركيب `pos_epson_printer`: حقوله
(`epson_printer_ip` على pos.printer و pos.config) تحمل عناوين الطابعات الفعلية،
وإلغاء التركيب مخاطرة على تلك البيانات بلا داعٍ — إزالة أصوله من الحزمة تكفي.

## بعد النشر

1. الموديول على الإصدار الجديد:

```bash
sudo -u postgres psql -d hosny -tAc \
  "select name, state, latest_version from ir_module_module \
    where name in ('hosny_pos_send_order','hosny_pos_printer_matrix');"

# وسجل إزالة الأصول موجود:
sudo -u postgres psql -d hosny -tAc \
  "select bundle, directive, path from ir_asset where path like '%pos_epson_printer%';"
```

2. الحزمة المنشورة تحتوي الكود الجديد ولا تحتوي القديم. الحزمة تُبنى عند أول
   فتح لنقطة البيع بمستخدم مسجَّل، فافتحها أولاً ثم:

```bash
sudo -u postgres psql -d hosny -tAc "select store_fname from ir_attachment \
  where url like '/web/assets/%' and name like '%point_of_sale.assets_prod.min.js%' \
  order by create_date desc limit 1;"
# في الملف الناتج: markPreparationSent يجب أن يوجد، و _printToKitchen يجب أن يكون صفراً
grep -c 'markPreparationSent' /opt/odoo19-data/filestore/hosny/<store_fname>
grep -c '_printToKitchen'     /opt/odoo19-data/filestore/hosny/<store_fname>
# والكلاس v17 المكسور يجب أن يكون صفراً:
grep -c "pos_epson_printer.ePOSLayout" /opt/odoo19-data/filestore/hosny/<store_fname>
```

3. **الاختبار الحقيقي من جهاز في الفرع** — لا يمكن التحقق منه من الخادم، فلا
   طريق من هنا إلى شبكات الفروع:
   - اضغط «إرسال الطلب» على طلب فيه أصناف: لا أخطاء في الـ console، ويظهر
     إشعار «... أُرسلت إلى المطبخ».
   - تذاكر التحضير تُطبع على الطابعة الصحيحة لكل قسم (لا على كل الطابعات).
   - عدد النسخ ونوع الفاتورة والقالب والتذكرة المجمّعة تتبع مصفوفة الطابعات.
   - العدّاد يظهر على الطاولة في شاشة الصالة ويستمر، ويظهر نفسه على جهاز آخر.
   - `select preparation_state, preparation_sent_at from pos_order order by id desc limit 5;`
     يجب أن يُظهر `sent` ووقتاً، لا `draft` و NULL.

## الرجوع

```bash
systemctl stop odoo19-hosny.service
rm -rf /opt/Hosney-Pos/custom_addons/hosny_pos_send_order
cp -a /opt/Hosney-Pos/tools/backups/hosny_pos_send_order-2026-09-23-pre-fix \
      /opt/Hosney-Pos/custom_addons/hosny_pos_send_order
psql -h 127.0.0.1 -U odoo19 -d hosny -c \
  "DELETE FROM ir_attachment WHERE url LIKE '/web/assets/%' AND name LIKE '%point_of_sale%';"
runuser -u odoo19 -- /opt/odoo19/venv/bin/python /opt/odoo19/odoo/odoo-bin \
  -c /etc/odoo19-hosny.conf -u hosny_pos_send_order --stop-after-init
systemctl start odoo19-hosny.service
rm -rf /var/cache/nginx/odoo_hosny/* && systemctl reload nginx
```

العمودان `preparation_state` / `preparation_sent_at` يبقيان في قاعدة البيانات
بعد الرجوع — لا يضرّان، والنسخة القديمة لا تكتب فيهما شيئاً أصلاً.
