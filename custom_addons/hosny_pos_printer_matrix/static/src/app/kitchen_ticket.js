/**
 * تذكرة المطبخ بتصميم FERP («نسخة المطبخ»): تجهيز البيانات والطباعة.
 *
 * القالب hosny_pos_printer_matrix.KitchenTicket يُرسم هنا ثم يمرّ على
 * printer.printReceipt كأي تذكرة أخرى (html-to-image ثم ePOS). اختيار القالب
 * لكل طابعة × نوع فاتورة يبقى في printer_matrix.js (report_template).
 */
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { renderToElement } from "@web/core/utils/render";
import { idsOf } from "./product_routing";

const { DateTime } = luxon;

// نص فيه كل ما تحتاجه التذكرة، حتى يحمّل المتصفح الخط كاملاً وليس جزءاً منه.
const FONT_SAMPLE = "نسخة المطبخ فاتورة مجمعة رقم الفاتورة الكـميه 0123456789 Cashier PM/:";
const KITCHEN_FONTS = [
    '400 30px "Hosny Kitchen Amiri"',
    '700 30px "Hosny Kitchen Amiri"',
    '400 30px "Hosny Kitchen Naskh"',
    '400 24px "Hosny Kitchen Tahoma"',
    '400 30px "Hosny Kitchen Serif"',
    '700 30px "Hosny Kitchen Serif"',
];
let kitchenFontsReady = null;

/**
 * يُقاس ارتفاع التذكرة في الصفحة قبل تحويلها لصورة، فلو لم يكن الخط محمّلاً
 * بعد لقيست بخط بديل وخرجت الصورة مقصوصة. نحمّل الخطوط مرة واحدة، ولا نحفظ
 * الوعد إلا لو نجح التحميل حتى تعيد التذكرة التالية المحاولة.
 */
export function loadKitchenFonts() {
    if (!kitchenFontsReady) {
        kitchenFontsReady = Promise.all(
            KITCHEN_FONTS.map((font) => document.fonts.load(font, FONT_SAMPLE))
        ).then(
            (faces) => {
                if (faces.some((list) => !list.length)) {
                    kitchenFontsReady = null;
                }
            },
            () => {
                kitchenFontsReady = null;
            }
        );
    }
    return kitchenFontsReady;
}

/** 1 → "1"، 0.5 → "0.5"، 0.250 → "0.25" */
export function formatKitchenQty(quantity) {
    const qty = Math.abs(Number(quantity) || 0);
    return Number.isInteger(qty) ? String(qty) : String(parseFloat(qty.toFixed(3)));
}

const splitNote = (note) =>
    String(note || "")
        .split("\n")
        .map((part) => part.trim())
        .filter(Boolean);

/**
 * السطر الأساسي لصنف ينزل تلقائياً معه (hosny_pos_meal_combo): الأصناف
 * الجانبية («ملوخية بالدجاج» ← ملوخية سادة + أرز) ومكوّنات الوجبة
 * («وجبة لمة حسني» ← أرز بسمتى + ملوخية سادة…).
 */
function addonParentUuid(line) {
    if (line?.is_additional_final_product && line.additional_final_parent_uuid) {
        return line.additional_final_parent_uuid;
    }
    if (line?.is_meal_component && line.meal_parent_uuid) {
        return line.meal_parent_uuid;
    }
    return false;
}

patch(PosOrder.prototype, {
    /**
     * نحفظ مع كل سطر جانبي مُرسل للمطبخ سطره الأساسي، حتى تعرف تذكرة الإلغاء
     * (بعد حذف السطر من الطلب) أنه تابع لصنف ولا تطبعه كصنف مستقل.
     */
    updateLastOrderChange() {
        const result = super.updateLastOrderChange(...arguments);
        const sent = this.last_order_preparation_change?.lines || {};
        for (const line of this.lines) {
            const resume = sent[line.preparationKey];
            const parentUuid = addonParentUuid(line);
            if (resume && parentUuid) {
                resume.hosny_addon_parent_uuid = parentUuid;
            }
        }
        return result;
    },
});

patch(PosStore.prototype, {
    /**
     * رقم الطلب في الوردية يعطيه الخادم عند أول مزامنة. نزامن الطلب الجديد في
     * الخلفية مع أول صنف يُضاف، فيظهر رقمه (1، 2، 3…) خلال لحظة بدل رقم الجهاز
     * المؤقت، ويطابق رقم تذكرة المطبخ والفاتورة.
     */
    async addLineToOrder(vals, order, ...rest) {
        const line = await super.addLineToOrder(vals, order, ...rest);
        this.hosnyRequestOrderNumber(order || this.getOrder());
        return line;
    },

    hosnyRequestOrderNumber(order) {
        if (
            !order ||
            order.finalized ||
            order.hosny_session_number ||
            typeof order.id === "number" ||
            !order.lines?.length ||
            this.data.network.offline
        ) {
            return;
        }
        this._hosnyNumbering ??= new Set();
        if (this._hosnyNumbering.has(order.uuid)) {
            return;
        }
        this._hosnyNumbering.add(order.uuid);
        Promise.resolve()
            .then(() => this.syncAllOrders({ orders: [order] }))
            .catch(() => {})
            .finally(() => this._hosnyNumbering.delete(order.uuid));
    },

    /** بيانات التذكرة التي لا يحملها getOrderData الأصلي. */
    getOrderData(order, reprint) {
        const data = super.getOrderData(order, reprint);
        const table = order?.table_id;
        // السفري بلا طاولة: سطر «طاوله» يبقى فارغاً (لا نطبع اسمه العائم فيه).
        data.hosny_table = table
            ? String(table.table_number ?? "")
            : this.isTakeawayOrder(order)
            ? ""
            : order?.floating_order_name || "";
        data.hosny_floor = table?.floor_id?.name || "";
        // «رقم الفاتورة»: رقم الطلب في الوردية (1، 2، 3…) من الخادم.
        data.hosny_order_number = order?.hosny_session_number
            ? String(order.hosny_session_number)
            : "";
        // نفس صيغة FERP: 9/26/2026 11:39:47 PM بغض النظر عن لغة الكاشير.
        // أودو يضبط أرقام luxon الافتراضية على الهندية للعربية، فنثبّتها لاتينية.
        data.hosny_printed_at = DateTime.now()
            .reconfigure({ locale: "en-US", numberingSystem: "latn", outputCalendar: "gregory" })
            .toFormat("M/d/yyyy h:mm:ss a");
        data.hosny_addon_parents = this.hosnyAddonParents(order);
        return data;
    },

    /**
     * الأصناف التي تنزل تلقائياً مع صنف أساسي (addonParentUuid) سطور حقيقية
     * في الطلب، فتصل للتذكرة كأصناف منفصلة. نحفظ هنا لكل سطر جانبي سطره الأساسي واسمه،
     * ومن ذاكرة آخر إرسال أيضاً لأن السطر الملغي لم يعد موجوداً في الطلب.
     */
    hosnyAddonParents(order) {
        const parents = {};
        for (const line of order?.lines || []) {
            const parentUuid = addonParentUuid(line);
            if (parentUuid) {
                parents[line.uuid] = parentUuid;
            }
        }
        const sent = order?.last_order_preparation_change?.lines || {};
        for (const resume of Object.values(sent)) {
            if (resume?.uuid && !parents[resume.uuid] && resume.hosny_addon_parent_uuid) {
                parents[resume.uuid] = resume.hosny_addon_parent_uuid;
            }
        }
        const nameOf = (uuid) =>
            this.models["pos.order.line"].getBy("uuid", uuid)?.getFullProductName?.() ||
            Object.values(sent).find((resume) => resume?.uuid === uuid)?.name ||
            "";
        const result = {};
        for (const [uuid, parentUuid] of Object.entries(parents)) {
            result[uuid] = { uuid: parentUuid, name: nameOf(parentUuid) };
        }
        return result;
    },

    /**
     * رقم الوردية يعطيه الخادم عند إنشاء الطلب، وأودو يطبع تذكرة الطلب الجديد
     * قبل أول مزامنة له. فلو الطلب بلا رقم بعد نرسله للخادم أولاً ثم نطبع؛
     * المزامنة اللاحقة للطباعة (في أودو) تبقى كما هي. لو فشلت هذه المزامنة لا
     * نوقف الطباعة: التذكرة تخرج برقم التتبّع كما كانت.
     */
    async sendOrderInPreparation(order, opts = {}) {
        if (
            order &&
            !opts.byPassPrint &&
            !order.hosny_session_number &&
            this.config.printerCategories.size &&
            !this.data.network.offline
        ) {
            try {
                await this.syncAllOrders({ orders: [order], force: true });
            } catch {
                // الطباعة أهم من الرقم
            }
        }
        return await super.sendOrderInPreparation(...arguments);
    },

    /**
     * أودو يميّز «جديد / ملغي / تعديل ملاحظة» بالعنوان المترجم فقط. نعلّم كل
     * تذكرة بنوعها هنا بنفس ترتيب بنائها في الأصل، حتى لا نقارن نصوصاً
     * مترجمة (المتر لغته en_US والكاشير ar_001).
     */
    async generateReceiptsDataToPrint(orderData, changes, orderChange) {
        const receipts = await super.generateReceiptsDataToPrint(...arguments);
        const kinds = [];
        if (changes.new?.length) {
            kinds.push("new");
        }
        if (changes.cancelled?.length) {
            kinds.push("cancelled");
        }
        if (changes.noteUpdate?.length) {
            kinds.push("noteUpdate");
        }
        if (orderChange?.internal_note || orderChange?.general_customer_note) {
            kinds.push("notes");
        }
        if (kinds.length === receipts.length) {
            receipts.forEach((receipt, index) => (receipt.hosny_kind = kinds[index]));
        }
        return receipts;
    },

    /** نوع التذكرة، مع الرجوع للعنوان لو لم تمر عبر generateReceiptsDataToPrint. */
    kitchenTicketKind(data) {
        if (data.hosny_kind) {
            return data.hosny_kind;
        }
        const title = String(data.changes?.title || "");
        if (title === String(_t("NEW"))) {
            return "new";
        }
        if (title === String(_t("CANCELLED"))) {
            return "cancelled";
        }
        return data.changes?.data?.length ? "noteUpdate" : "notes";
    },

    /**
     * مجموعة الوجبات (pos.category) التي يظهر تحتها الصنف: أول مجموعة للصنف
     * تقبلها هذه الطابعة (مباشرة أو عبر مجموعة أب)، وإلا أول مجموعة له —
     * وهذا حال التذكرة المجمّعة والأصناف المختارة يدوياً على الطابعة.
     */
    kitchenCategoryFor(productId, printerCategoryIds) {
        const product = this.models["product.product"].get(productId);
        const categories = product?.pos_categ_ids || [];
        if (!categories.length) {
            return null;
        }
        if (printerCategoryIds.size) {
            const accepted = categories.find(
                (categ) =>
                    printerCategoryIds.has(categ.id) ||
                    (categ.allParents || []).some((parent) => printerCategoryIds.has(parent.id))
            );
            if (accepted) {
                return accepted;
            }
        }
        return categories[0];
    },

    /** يحوّل تغييرات التذكرة إلى مجموعات وأصناف جاهزة للقالب. */
    buildKitchenTicket(data, printer) {
        const raw = printer?.config?.raw || printer?.config || {};
        const printerCategoryIds = new Set(idsOf(raw.product_categories_ids));
        const groups = new Map();
        const groupOfLine = new Map();
        const lineOfUuid = new Map();

        // الصنف الجانبي الذي يطبع على نفس التذكرة مع صنفه الأساسي يُكتب
        // تحت الأساسي («+ ملوخية سادة») لا في سطر مستقل. لو طُبع وحده في
        // محطة أخرى يبقى سطراً وتحته «مع: <الصنف الأساسي>».
        const addonParents = data.hosny_addon_parents || {};
        const changes = data.changes?.data || [];
        const uuidsOnTicket = new Set(changes.map((change) => change.uuid).filter(Boolean));
        const addons = [];

        for (const change of changes) {
            const parent = change.uuid && addonParents[change.uuid];
            if (parent && uuidsOnTicket.has(parent.uuid)) {
                addons.push({ change, parentUuid: parent.uuid });
                continue;
            }
            // مكوّنات الكومبو تبقى تحت الكومبو نفسه
            let group = change.combo_parent_uuid && groupOfLine.get(change.combo_parent_uuid);
            if (!group) {
                const categ = this.kitchenCategoryFor(change.product_id, printerCategoryIds);
                const key = categ ? `categ-${categ.id}` : "categ-none";
                group = groups.get(key);
                if (!group) {
                    group = {
                        key,
                        name: categ?.name || "",
                        sequence: categ?.sequence ?? Number.MAX_SAFE_INTEGER,
                        id: categ?.id ?? Number.MAX_SAFE_INTEGER,
                        lines: [],
                    };
                    groups.set(key, group);
                }
            }
            if (change.uuid) {
                groupOfLine.set(change.uuid, group);
            }
            // ملاحظة الصنف في مربع مستقل عن الخيارات («- ربع كيلو»)، حتى لا
            // تُقرأ كخيار آخر ويفوتها الطباخ.
            const lineNotes = [...splitNote(change.note), ...splitNote(change.customer_note)];
            const details = (change.attribute_value_names || []).map((name) => ({
                text: `- ${name}`,
                isNote: false,
            }));
            if (lineNotes.length) {
                details.push({ text: `ملاحظة: ${lineNotes.join("، ")}`, isNote: true });
            }
            if (parent?.name) {
                details.unshift({ text: `مع: ${parent.name}`, isNote: false });
            }
            const line = {
                name: change.basic_name || change.name || change.display_name || "",
                qty: formatKitchenQty(change.quantity),
                quantity: change.quantity,
                details,
                comboChild: Boolean(change.combo_parent_uuid),
            };
            group.lines.push(line);
            if (change.uuid) {
                lineOfUuid.set(change.uuid, line);
            }
        }

        // الجانبي تحت أساسيه، قبل ملاحظة الأساسي حتى تبقى الملاحظة آخر شيء.
        // الكمية تُكتب فقط لو اختلفت عن كمية الأساسي (½ طبق محاشى مع وجبة).
        for (const { change, parentUuid } of addons) {
            const parentLine = lineOfUuid.get(parentUuid);
            if (!parentLine) {
                continue;
            }
            const name = change.basic_name || change.name || change.display_name || "";
            const extras = [
                ...(change.attribute_value_names || []),
                ...splitNote(change.note),
                ...splitNote(change.customer_note),
            ];
            let text = `+ ${name}`;
            if (Math.abs(change.quantity) !== Math.abs(parentLine.quantity)) {
                text += ` ×${formatKitchenQty(change.quantity)}`;
            }
            if (extras.length) {
                text += ` (${extras.join("، ")})`;
            }
            const noteAt = parentLine.details.findIndex((detail) => detail.isNote);
            parentLine.details.splice(noteAt === -1 ? parentLine.details.length : noteAt, 0, {
                text,
                isNote: false,
            });
        }

        const kind = this.kitchenTicketKind(data);
        // «تعديل ملاحظة» لصنف بلا ملاحظة الآن = الملاحظة حُذفت؛ نقولها صراحة.
        if (kind === "noteUpdate") {
            for (const group of groups.values()) {
                for (const line of group.lines) {
                    if (!line.details.some((detail) => detail.isNote)) {
                        line.details.push({ text: "أُلغيت الملاحظة", isNote: true });
                    }
                }
            }
        }
        const statusByKind = {
            cancelled: "إلغاء",
            noteUpdate: "تعديل ملاحظة",
            notes: data.hosny_order_note_removed ? "إلغاء ملاحظة الطلب" : "ملاحظة على الطلب",
        };
        let status = statusByKind[kind] || "";
        if (data.reprint) {
            status = status ? `${status} (نسخة مكررة)` : "نسخة مكررة";
        }

        // ملاحظة الطلب: في تذكرتها الخاصة، وفي تذكرة الأصناف الجديدة حين
        // تحملها (printChanges في printer_matrix.js يقرر أيّهما).
        const notes = [];
        if (kind === "notes" || data.hosny_show_order_note) {
            if (data.internal_note) {
                notes.push({ label: "ملاحظة الطلب: ", text: data.internal_note });
            }
            if (data.general_customer_note) {
                notes.push({ label: "ملاحظة العميل: ", text: data.general_customer_note });
            }
            if (!notes.length && data.hosny_order_note_removed) {
                notes.push({ label: "", text: "أُلغيت ملاحظة الطلب السابقة" });
            }
        }

        return {
            kind,
            status,
            notes,
            groups: [...groups.values()].sort(
                (a, b) => a.sequence - b.sequence || a.id - b.id
            ),
        };
    },

    async printKitchenTicket(data, printer) {
        await loadKitchenFonts();
        const ticket = this.buildKitchenTicket(data, printer);
        const receipt = renderToElement("hosny_pos_printer_matrix.KitchenTicket", {
            data,
            ticket,
        });
        return await printer.printReceipt(receipt);
    },
});
