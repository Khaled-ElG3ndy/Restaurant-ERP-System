/** مصفوفة الطابعات: نوع الفاتورة + عدد النسخ + قالب التذكرة + التذكرة المجمّعة */
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { RetryPrintPopup } from "@point_of_sale/app/components/popups/retry_print_popup/retry_print_popup";
import { changesToOrder } from "@point_of_sale/app/models/utils/order_change";
import { patch } from "@web/core/utils/patch";
import { renderToElement } from "@web/core/utils/render";
import { idsOf } from "./product_routing";

const relId = (v) => (v && typeof v === "object" ? v.id : v) ?? null;

patch(PosStore.prototype, {
    /** النوع الافتراضي، يُستخدم لأي طلب لم يُختر له نوع بعد. */
    get defaultOrderType() {
        const types = this.models["pos.order.type"]?.getAll?.() || [];
        return types.find((t) => t.is_default) || types[0] || null;
    },

    /**
     * نوع الطلب الفعّال: المختار، وإلا الافتراضي. طلب بلا نوع وبلا طاولة لا
     * يُعتبر محلياً (order_type_rules.js يعطي كل طلب جديد نوعه، فهذا للقديم فقط).
     */
    getEffectiveOrderType(order) {
        if (order?.order_type_id) {
            return order.order_type_id;
        }
        if (order && this.config.module_pos_restaurant && !order.table_id && this.takeawayOrderType) {
            return this.takeawayOrderType;
        }
        return this.defaultOrderType;
    },

    /** نمرّر نوع الفاتورة مع بيانات التذكرة حتى تصل إلى طبقة الطباعة. */
    getOrderData(order, reprint) {
        const data = super.getOrderData(order, reprint);
        const type = this.getEffectiveOrderType(order);
        data.order_type_id = relId(type);
        data.order_type_name = (type && type.name) || "";
        return data;
    },

    /** سطر المصفوفة لهذه الطابعة ونوع الفاتورة، أو undefined لو غير معرّف. */
    getPrinterMatrixLine(printer, orderTypeId) {
        const lines = this.models["pos.printer.line"]?.getAll?.() || [];
        const printerId = printer?.config?.id;
        return lines.find(
            (l) =>
                relId(l.printer_id) === printerId &&
                relId(l.order_type_id) === orderTypeId
        );
    },

    /** قالب التذكرة لسطر المصفوفة: FERP افتراضياً لو لا يوجد سطر. */
    kitchenTemplateFor(line, bundled) {
        if (!line) {
            return "ferp";
        }
        return (bundled ? line.bundled_report : line.report_template) || "ferp";
    },

    /**
     * تُستدعى مرة لكل تذكرة لكل طابعة. نضيف هنا ثلاث سلوكيات:
     *   • تخطّي الطابعة لو النوع غير مفعّل لها
     *   • تكرار الطباعة بعدد النسخ
     *   • اختيار قالب التذكرة
     * لو لا يوجد سطر مصفوفة: نسخة واحدة بقالب FERP (القالب الافتراضي).
     */
    async printOrderChanges(data, printer) {
        const line = this.getPrinterMatrixLine(printer, data.order_type_id);
        if (line && !line.enabled) {
            return { successful: true };
        }

        const bundled = data._bundled === true;
        let copies = 1;
        const template = this.kitchenTemplateFor(line, bundled);
        if (line) {
            copies = bundled ? line.bundled_copies : line.copies;
        }

        let result = { successful: true };
        for (let i = 0; i < Math.max(copies || 0, 0); i++) {
            // القالب القياسي يمرّ عبر super حتى تبقى تعديلات الموديولات
            // الأخرى على الطباعة سارية؛ FERP والمختصرة نرسمهما بأنفسنا.
            if (template === "standard") {
                result = await super.printOrderChanges(data, printer);
            } else if (template === "compact") {
                result = await printer.printReceipt(
                    renderToElement("hosny_pos_printer_matrix.OrderChangeReceiptCompact", {
                        data,
                    })
                );
            } else {
                result = await this.printKitchenTicket(data, printer);
            }
            if (!result.successful) {
                break;
            }
        }
        return result;
    },

    /** كل مجموعات الوجبات — نمرّرها لـ generateOrderChange ثم نفلتر بأنفسنا. */
    get allPosCategoryIds() {
        return this.models["pos.category"].getAll().map((c) => c.id);
    },

    /** قاعدة الطابعة: (المجموعة مختارة أو الصنف مختار) وليس مستثنى. */
    printerAcceptsProduct(printer, productId) {
        const product = this.models["product.product"].get(productId);
        if (!product) {
            return false;
        }
        const raw = printer.config?.raw || printer.config || {};
        const tmplId = relId(product.product_tmpl_id);

        if (idsOf(raw.excluded_product_ids).includes(tmplId)) {
            return false;
        }
        if (idsOf(raw.product_ids).includes(tmplId)) {
            return true;
        }
        const cats = idsOf(raw.product_categories_ids);
        return (product.parentPosCategIds || []).some((c) => cats.includes(c));
    },

    /** نفس منطق الدمج في أودو (الكومبو يتبع مكوّناته) لكن بقاعدة الطابعة. */
    filterChangeForPrinter(printer, changes) {
        const matches = (c) => this.printerAcceptsProduct(printer, c["product_id"]);
        const filterChanges = (list) => {
            const validComboUuids = new Set(
                (list || [])
                    .filter((c) => c.combo_parent_uuid && matches(c))
                    .map((c) => c.combo_parent_uuid)
            );
            return (list || []).filter(
                (c) =>
                    (c.isCombo && validComboUuids.has(c.uuid)) ||
                    (!c.isCombo && matches(c))
            );
        };
        return {
            new: filterChanges(changes.new),
            cancelled: filterChanges(changes.cancelled),
            noteUpdate: filterChanges(changes.noteUpdate),
        };
    },

    /** هل تحضّر هذه الطابعة شيئاً من أصناف الطلب الحالية؟ */
    printerServesOrder(printer, order) {
        return (order?.lines || []).some((line) =>
            this.printerAcceptsProduct(printer, line.product_id?.id)
        );
    },

    /** ملاحظة الطلب (الداخلية + ملاحظة العميل) كنص يُطبع؛ "" لو لا توجد. */
    hosnyOrderNoteText(internalNote, customerNote) {
        return [this.getStrNotes(internalNote || ""), String(customerNote || "").trim()]
            .filter(Boolean)
            .join(" | ");
    },

    /**
     * تغيّر نص ملاحظة الطلب في هذا الإرسال؟ يُحسب مرة واحدة ويُحفظ على
     * التغيير نفسه قبل updateLastOrderChange، فيبقى صحيحاً في إعادة المحاولة
     * وإعادة الطباعة. "" ← "[]" ليس تغييراً (نفس النص الفارغ).
     */
    hosnyMarkOrderNoteChange(order, change) {
        if (!change || change.hosny_order_note_changed !== undefined) {
            return;
        }
        if (change.internal_note === undefined && change.general_customer_note === undefined) {
            change.hosny_order_note_changed = false;
            return;
        }
        const last = order?.last_order_preparation_change || {};
        const before = this.hosnyOrderNoteText(last.internal_note, last.general_customer_note);
        const after = this.hosnyOrderNoteText(order?.internal_note, order?.general_customer_note);
        change.hosny_order_note_changed = before !== after;
    },

    /**
     * أودو لا يطبع شيئاً حين يكون التغيير الوحيد حذف ملاحظة الطلب: القيمة
     * الجديدة فارغة، وشرط الطباعة عنده هو أن تكون غير فارغة. فيبقى المطبخ
     * على ملاحظة لم تعد موجودة («بدون ملح» مثلاً).
     */
    hosnyOnlyOrderNoteRemoved(order) {
        const change = changesToOrder(order, this.config.printerCategories, false);
        if (
            change.new.length ||
            change.cancelled.length ||
            change.noteUpdate.length ||
            change.internal_note ||
            change.general_customer_note
        ) {
            return false;
        }
        const last = order.last_order_preparation_change || {};
        return (
            Boolean(this.hosnyOrderNoteText(last.internal_note, last.general_customer_note)) &&
            !this.hosnyOrderNoteText(order.internal_note, order.general_customer_note)
        );
    },

    /**
     * «سفري» وحده تخرج فاتورة عميله مع أول إرسال للطلب. تذاكر التحضير نفسها
     * تُطبع عند «إرسال الطلب» للسفري والمحلي معاً.
     */
    hosnyIsSafariOrder(order) {
        return this.getEffectiveOrderType(order)?.code === "safari";
    },

    /**
     * فاتورة العميل للسفري تخرج مرة واحدة مع أول إرسال للطلب. نميّز أول
     * إرسال من آخر تغيير أُرسل للمطبخ، لا من رقم الفاتورة، لأن الرقم يُعطى
     * للطلب قبل الطباعة كي يظهر على تذكرة التحضير.
     */
    hosnyNeedsTakeawayCustomerReceipt(order, opts = {}) {
        // 2026-10-09 (خالد): «إرسال الطلب» يطبع تذاكر الأقسام فقط؛ فاتورة العميل
        // للسفري تُطبع بعد الدفع (نسختان، takeaway_checkout في pos_entry_selector).
        // hosnyTakeawayReceiptAtSend = true يعيد السلوك القديم (غير مضبوط افتراضياً).
        if (!this.hosnyTakeawayReceiptAtSend) {
            return false;
        }
        if (
            !order ||
            order.finalized ||
            opts.byPassPrint ||
            opts.cancelled ||
            opts.explicitReprint ||
            !this.hosnyIsSafariOrder(order) ||
            !order.lines?.length
        ) {
            return false;
        }
        return !Object.keys(order.last_order_preparation_change?.lines || {}).length;
    },

    async hosnyPrintTakeawayCustomerReceipt(order) {
        try {
            // هذا هو مسار فاتورة العميل العادي (طابعة الكاشير أو طباعة
            // المتصفح عند عدم وجود جهاز)، وليس مسار طابعات التحضير.
            // printBillActionTriggered يمنع أودو من كتابة nb_print بطلب
            // مستقل؛ ذلك الطلب كان يتزامن مع sync_from_ui للطلب نفسه فيصطدم
            // به («could not serialize»). نعدّ النسخة محلياً بعد المزامنة
            // (أسفل sendOrderInPreparation).
            const result = await this.printReceipt({ order, printBillActionTriggered: true });
            if (result) {
                order.uiState.hosnyReceiptPrinted = true;
            }
        } catch (error) {
            // فشل الفاتورة لا يعطّل حفظ الطلب أو تذكرة المطبخ؛ خدمة الطباعة
            // نفسها تعرض محاولة إعادة الطباعة للكاشير عند وجود طابعة فعلية.
            console.warn("[Hosny] takeaway customer receipt failed", error);
        }
    },

    async sendOrderInPreparation(order, opts = {}) {
        const shouldPrintCustomerReceipt = this.hosnyNeedsTakeawayCustomerReceipt(order, opts);

        if (
            order &&
            !opts.byPassPrint &&
            !opts.cancelled &&
            this.config.printerCategories.size &&
            this.hosnyOnlyOrderNoteRemoved(order)
        ) {
            // نفس ذيل الأصل: نطبع، نحدّث «آخر ما أُرسل»، ثم نزامن.
            let isPrinted = false;
            try {
                const change = changesToOrder(order, this.config.printerCategories, false);
                order.uiState.lastPrints.push(change);
                isPrinted = await this.printChanges(order, [change], false);
            } catch (error) {
                console.warn("[Hosny] order note removal ticket failed", error);
            }
            order.updateLastOrderChange();
            if (isPrinted && !this.models["pos.prep.display"]?.length) {
                await this.syncAllOrders({ orders: [order] });
            }
            return;
        }
        // لا ننتظر شبكة طابعات المطبخ واحدةً تلو الأخرى قبل بدء فاتورة
        // العميل. رقم الوردية جاهز هنا (تزامن kitchen_ticket سبقنا)، لذا
        // تبدأ الفاتورة فوراً بالتوازي مع تذاكر التحضير ثم ننتظر المسارين
        // قبل إنهاء الإرسال.
        const customerReceiptJob = shouldPrintCustomerReceipt
            ? this.hosnyPrintTakeawayCustomerReceipt(order)
            : null;
        const result = await super.sendOrderInPreparation(...arguments);
        if (customerReceiptJob) {
            await customerReceiptJob;
            // بعد انتهاء المزامنة داخل super فقط: لو عدّلناه أثناءها يعيده رد
            // الخادم صفراً. يصل للخادم مع المزامنة التالية (الدفع).
            if (order.uiState.hosnyReceiptPrinted && !order.nb_print) {
                order.nb_print = 1;
            }
        }
        return result;
    },

    /**
     * نعيد بناء الحلقة بدل استدعاء super لأن فلتر أودو يستقبل قائمة مجموعات
     * فقط ولا يعرف أي طابعة يفلتر لها، فلا مكان فيه لقاعدة الصنف.
     * نمرّر كل المجموعات لـ generateOrderChange (ليبقى الترتيب ومعالجة
     * الكومبو والملاحظات كما هي) ثم نطبّق قاعدة الطابعة بأنفسنا.
     */
    async printChanges(
        order,
        orderChange,
        reprint = false,
        printers = this.unwatched.printers,
        bundledPrinters = printers
    ) {
        let isPrinted = false;
        const unsuccessfulPrints = [];
        // إعادة المحاولة لكل تمريرة على حدة: فشل المجمّعة وحدها لا يعيد طباعة
        // تذكرة المحطة التي خرجت بالفعل، والعكس.
        const retryPrinters = new Set();
        const retryBundledPrinters = new Set();
        const allCategories = this.allPosCategoryIds;
        const orderTypeId = relId(this.getEffectiveOrderType(order));
        for (const change of orderChange) {
            this.hosnyMarkOrderNoteChange(order, change);
        }
        const orderServedAnywhere = this.unwatched.printers.some((printer) =>
            this.printerServesOrder(printer, order)
        );
        // المجمّعة تخص الطلب كله، حتى أقسامه التي لا طابعة لها.
        const orderHasLines = Boolean(order?.lines?.length);

        const runPass = async (printer, change, bundled) => {
            const { orderData, changes } = this.generateOrderChange(
                order,
                change,
                allCategories,
                reprint
            );
            // التذكرة المجمّعة تحتوي كل المحطات، وإلا قاعدة هذه الطابعة.
            const mine = bundled
                ? changes
                : this.filterChangeForPrinter(printer, changes);
            const hasItems =
                mine.new.length || mine.cancelled.length || mine.noteUpdate.length;
            // ملاحظة الطلب تخص كل محطة تحضّر شيئاً من الطلب، لا المحطات التي
            // وصلتها أصناف في هذا الإرسال فقط. قبل هذا كانت ملاحظة الطلب
            // المُرسلة وحدها لا تُطبع في أي طابعة.
            const noteForPrinter =
                Boolean(change.hosny_order_note_changed) &&
                (bundled ? orderHasLines || orderServedAnywhere : this.printerServesOrder(printer, order));
            if (!hasItems && !noteForPrinter) {
                return;
            }
            if (bundled) {
                orderData._bundled = true;
            }
            // تذكرة الملاحظة المنفصلة نبنيها نحن أدناه، فلا نطلبها من أودو.
            const receiptsData = await this.generateReceiptsDataToPrint(orderData, mine, {
                ...change,
                internal_note: undefined,
                general_customer_note: undefined,
            });
            // FERP والمختصرة تطبعان ملاحظة الطلب داخل تذكرة الأصناف الجديدة،
            // فتصل الطباخ مع الأصناف نفسها. القياسية (قالب أودو) لا تعرضها إلا
            // في تذكرة الملاحظة المنفصلة كما في الأصل.
            const template = this.kitchenTemplateFor(
                this.getPrinterMatrixLine(printer, orderTypeId),
                bundled
            );
            const hasOrderNote = Boolean(orderData.internal_note || orderData.general_customer_note);
            let noteCarried = false;
            if (template !== "standard" && hasOrderNote) {
                for (const data of receiptsData) {
                    if (data.hosny_kind === "new") {
                        data.hosny_show_order_note = true;
                        noteCarried = true;
                    }
                }
            }
            if (noteForPrinter && !noteCarried && (hasOrderNote || template !== "standard")) {
                receiptsData.push({
                    ...orderData,
                    changes: { title: "", data: [] },
                    hosny_kind: "notes",
                    hosny_show_order_note: true,
                    hosny_order_note_removed: !hasOrderNote,
                });
            }
            for (const data of receiptsData) {
                const result = await this.printOrderChanges(data, printer);
                if (result.successful) {
                    isPrinted = true;
                    if (result.warningCode) {
                        this.displayPrinterWarning(result, printer.config.name);
                    }
                } else {
                    (bundled ? retryBundledPrinters : retryPrinters).add(printer);
                    unsuccessfulPrints.push(
                        printer.config.name + ": " + result.message.body
                    );
                }
            }
        };

        // كل طابعة جهاز مستقل: نرسل للمحطات كلها في نفس الوقت بدل أن تنتظر
        // الكفتريا انتهاء المطبخ. داخل الطابعة الواحدة تبقى التذاكر بالترتيب:
        // تذكرة المحطة أولاً ثم المجمّعة (Bundeled Receipt)، فلا يصل جهازاً
        // واحداً طلبان في نفس اللحظة ولا تنتظر المجمّعة أبطأ محطة أخرى.
        // «إعادة المحاولة» تمرّر الطابعات كـ Set، فننسخها لمصفوفة.
        const normalSet = new Set(printers);
        const bundledSet = new Set(bundledPrinters);
        await Promise.all(
            [...new Set([...normalSet, ...bundledSet])].map(async (printer) => {
                if (normalSet.has(printer)) {
                    for (const change of orderChange) {
                        await runPass(printer, change, false);
                    }
                }
                if (!bundledSet.has(printer)) {
                    return;
                }
                const line = this.getPrinterMatrixLine(printer, orderTypeId);
                if (!line || !line.enabled || !line.bundled) {
                    return;
                }
                for (const change of orderChange) {
                    await runPass(printer, change, true);
                }
            })
        );

        if (unsuccessfulPrints.length) {
            this.dialog.add(RetryPrintPopup, {
                message: unsuccessfulPrints.join("\n"),
                canRetry: true,
                retry: () => {
                    this.printChanges(order, orderChange, reprint, retryPrinters, retryBundledPrinters);
                },
            });
        }
        return isPrinted;
    },
});
