/** @odoo-module **/
/**
 * «عرض الطلب كاملاً» (طلب 2026-09-28).
 *
 * زر تكبير في ركن قائمة الأصناف يفتح نافذة بكل أسطر الطلب مرتّبة، ومعها
 * ملاحظات المطبخ على كل صنف وعلى الطلب كله.
 *
 * الملاحظات هي حقول أودو نفسها وليست نصاً على الشاشة فقط:
 *   • ملاحظة الصنف  → pos.order.line.note
 *   • ملاحظة الطلب  → pos.order.internal_note
 * كلاهما مصفوفة JSON من {text, colorIndex} كما يكتبها زر «الملاحظات» في أودو،
 * فتُحفظ مع الطلب على الخادم، ويعدّها getOrderChanges تغييراً يستحق الإرسال
 * (فيعود زر «إرسال الطلب» فعّالاً)، وتطبعها تذكرة المطبخ. لا حقول جديدة.
 *
 * ملاحظة السطر تخص السطر كله: لو كان قد أُرسل للمطبخ تخرج تذكرة «تعديل
 * ملاحظة» بكميته كاملة. لصنف مختلف (واحد بدون بصل من اثنين) يُضاف الصنف
 * مرة ثانية، وأودو لا يدمج سطرين ملاحظاتهما مختلفة.
 */
import { Component, onWillUnmount, useEffect, useRef, useState, useSubEnv } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { OrderSummary } from "@point_of_sale/app/screens/product_screen/order_summary/order_summary";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { PosStore } from "@point_of_sale/app/services/pos_store";

export const HOSNY_NOTE_MAX_LENGTH = 120;
const ORDER_KEY = "order";

/**
 * يقرأ ملاحظة بأي شكل وصلت: مصفوفة JSON (أودو 19)، أو نص عادي من بيانات
 * أقدم. يرجع دائماً [{text, colorIndex}] بلا عناصر فارغة.
 */
export function hosnyParseNotes(raw) {
    if (!raw) {
        return [];
    }
    let parsed = raw;
    if (typeof raw === "string") {
        try {
            parsed = JSON.parse(raw);
        } catch {
            parsed = raw;
        }
    }
    if (!Array.isArray(parsed)) {
        const text = typeof parsed === "string" ? parsed.trim() : String(raw).trim();
        return text && text !== "null" ? [{ text, colorIndex: 0 }] : [];
    }
    return parsed
        .map((note) =>
            typeof note === "string"
                ? { text: note.trim(), colorIndex: 0 }
                : { text: String(note?.text ?? "").trim(), colorIndex: Number(note?.colorIndex) || 0 }
        )
        .filter((note) => note.text);
}

const sameText = (a, b) => a.trim().toLocaleLowerCase() === b.trim().toLocaleLowerCase();

/** صنف واحد، صنفان، ٣–١٠ أصناف، ١١ صنفاً فأكثر. */
function hosnyItemCount(count) {
    if (count === 1) {
        return "صنف واحد";
    }
    if (count === 2) {
        return "صنفان";
    }
    if (count >= 3 && count <= 10) {
        return `${count} أصناف`;
    }
    return `${count} صنفاً`;
}

export class HosnyOrderExpandDialog extends Component {
    static template = "hosny_pos_controls.OrderExpandDialog";
    static components = { Dialog };
    static props = {
        orderUuid: String,
        isSending: { type: Function, optional: true },
        sendOrder: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.pos = usePos();
        this.state = useState({ editing: null, drafts: {} });
        this.lineInput = useRef("lineNoteInput");
        this.maxLength = HOSNY_NOTE_MAX_LENGTH;
        this.closing = false;

        // الطلب لم يعد هو المعروض (مزامنة من جهاز آخر، قفل الكاشير، دفع…):
        // لا نترك نافذة تعدّل طلباً غير الذي أمام الكاشير.
        useEffect(
            (current, alive) => {
                if (!alive || current !== this.props.orderUuid) {
                    this.close({ commit: false });
                }
            },
            () => [this.pos.getOrder()?.uuid, Boolean(this.order && !this.order.finalized)]
        );

        // فتح محرر سطر ينقل التركيز إلى حقله مباشرة.
        useEffect(
            (editing) => {
                if (editing && editing !== ORDER_KEY) {
                    this.lineInput.el?.focus();
                }
            },
            () => [this.state.editing]
        );

        // ما كتبه الكاشير ولم يضغط «إضافة» لا يضيع عند الإغلاق بـ Esc أو ×.
        onWillUnmount(() => this.commitDrafts());
    }

    get order() {
        return this.pos.models["pos.order"].getBy("uuid", this.props.orderUuid);
    }

    get editable() {
        const order = this.order;
        return Boolean(order && !order.finalized && order.state === "draft");
    }

    /** نفس ترتيب قائمة الطلب: مكوّنات الكومبو تحت الكومبو مباشرة. */
    get rows() {
        const order = this.order;
        if (!order) {
            return [];
        }
        const rows = [];
        let index = 0;
        for (const line of order.lines) {
            if (line.combo_parent_id) {
                continue;
            }
            index += 1;
            rows.push({ line, index, child: false });
            for (const child of line.combo_line_ids || []) {
                rows.push({ line: child, index: null, child: true });
            }
        }
        return rows;
    }

    get itemCountLabel() {
        const count = (this.order?.lines || []).filter((line) => !line.combo_parent_id).length;
        return hosnyItemCount(count);
    }

    get placeLabels() {
        const order = this.order;
        if (!order) {
            return [];
        }
        const labels = [];
        const type = this.pos.getEffectiveOrderType?.(order);
        if (type?.name) {
            labels.push(type.name);
        }
        const table = order.table_id;
        if (table) {
            const floor = table.floor_id?.name;
            labels.push(`طاولة ${table.table_number ?? ""}`.trim() + (floor ? ` · ${floor}` : ""));
        } else if (order.floating_order_name && !this.pos.isTakeawayOrder?.(order)) {
            labels.push(order.floating_order_name);
        }
        if (order.hosny_session_number) {
            labels.push(`فاتورة رقم ${order.hosny_session_number}`);
        }
        return labels;
    }

    /**
     * ما أُرسل للمطبخ وما ينتظر، بتعريف أودو نفسه (getOrderChanges) الذي يحسب
     * منه زر «إرسال الطلب». الصنف الذي لا يُحضَّر في أي طابعة لا يظهر في
     * أيّ من المجموعتين، فلا تُعرض له حالة.
     */
    get kitchen() {
        const order = this.order;
        if (!order) {
            return { pending: new Set(), sent: new Set(), orderNotePending: false };
        }
        const changes = this.pos.getOrderChanges(order);
        const pending = new Set(
            [
                ...Object.values(changes.orderlines || {}),
                ...Object.values(changes.noteUpdate || {}),
            ].map((change) => change.uuid)
        );
        const sent = new Set(
            Object.values(order.last_order_preparation_change?.lines || {}).map((line) => line.uuid)
        );
        return {
            pending,
            sent,
            orderNotePending:
                changes.internal_note !== undefined || changes.general_customer_note !== undefined,
        };
    }

    lineStatus(line, kitchen) {
        const pending = kitchen.pending.has(line.uuid);
        const sent = kitchen.sent.has(line.uuid);
        if (pending && sent) {
            return { key: "changed", label: "تعديل لم يُرسل", icon: "fa-pencil" };
        }
        if (pending) {
            return { key: "new", label: "لم يُرسل بعد", icon: "fa-clock-o" };
        }
        if (sent) {
            return { key: "sent", label: "أُرسل للمطبخ", icon: "fa-check" };
        }
        return null;
    }

    lineView(line) {
        const qty = line.getQuantityStr?.() || {};
        const discount = line.combo_parent_id ? 0 : line.getDiscount();
        return {
            name: line.product_id?.name || line.getFullProductName(),
            attributes: line.orderDisplayProductName?.attributeString || "",
            qty: qty.qtyStr ?? String(line.qty),
            total: line.combo_parent_id ? "" : line.currencyDisplayPrice,
            // سعر الوحدة يفيد مع ٢ أو ٠٫٧٥ كيلو، لا مع السمك الموزون بالجرام
            // (١٧٥٠ × ٠٫٠٦٩) حيث يُقرَّب إلى ٠٫٠٧ ويضلّل.
            unitPrice:
                !line.combo_parent_id &&
                line.qty !== 1 &&
                Math.abs(line.qty) < 100 &&
                line.displayPriceUnit
                    ? line.currencyDisplayPriceUnit
                    : "",
            discount: discount ? `${discount}%` : "",
            hospitality: Boolean(line.is_hospitality),
            notes: hosnyParseNotes(line.getNote()),
        };
    }

    get orderNotes() {
        return hosnyParseNotes(this.order?.internal_note);
    }

    /**
     * حالة الإرسال بنفس قاعدة زر «إرسال الطلب» (hosnySendState): ما ينتظر =
     * أسطر تغيّرت كميتها أو ملاحظتها، أو ملاحظة الطلب. «أُرسل» = لا شيء ينتظر
     * والطلب وصل المطبخ من قبل.
     */
    sendInfo(kitchen) {
        const order = this.order;
        const pending = Boolean(kitchen.pending.size || kitchen.orderNotePending);
        const everSent =
            order?.preparation_state === "sent" ||
            Object.keys(order?.last_order_preparation_change?.lines || {}).length > 0;
        return { pending, sent: !pending && everSent, count: kitchen.pending.size };
    }

    get hasDrafts() {
        return Object.values(this.state.drafts).some((text) => text && text.trim());
    }

    canSend(info) {
        return Boolean(
            this.editable &&
                this.props.sendOrder &&
                (info.pending || this.hasDrafts) &&
                !this.props.isSending?.()
        );
    }

    /**
     * الملاحظات الجاهزة: «نماذج الملاحظات» المعرّفة لنقطة البيع (pos.note)،
     * ولسطر: ما كُتب على الأصناف الأخرى في هذا الطلب أيضاً («بدون ملح» لصنف
     * ثانٍ بلمسة). بلا تكرار وبلا ما على الهدف أصلاً.
     */
    quickNotes(existing, forLine = true) {
        const seen = new Set(existing.map((note) => note.text.trim().toLocaleLowerCase()));
        const result = [];
        const push = (text, colorIndex = 0) => {
            const key = (text || "").trim().toLocaleLowerCase();
            if (key && !seen.has(key)) {
                seen.add(key);
                result.push({ text: text.trim(), colorIndex });
            }
        };
        for (const note of this.pos.models["pos.note"]?.getAll?.() || []) {
            push(note.name, note.color || 0);
        }
        if (forLine) {
            for (const line of this.order?.lines || []) {
                for (const note of hosnyParseNotes(line.getNote())) {
                    push(note.text, note.colorIndex);
                }
            }
        }
        return result.slice(0, 12);
    }

    colorFor(text) {
        const preset = (this.pos.models["pos.note"]?.getAll?.() || []).find((note) =>
            sameText(note.name || "", text)
        );
        return preset?.color || 0;
    }

    // ── الكتابة على الطلب ────────────────────────────────────────────────

    notesOf(key) {
        if (key === ORDER_KEY) {
            return this.orderNotes;
        }
        const line = this.pos.models["pos.order.line"].getBy("uuid", key);
        return line ? hosnyParseNotes(line.getNote()) : null;
    }

    writeNotes(key, notes) {
        if (!this.editable) {
            return false;
        }
        const clean = notes.map((note) => ({ text: note.text, colorIndex: note.colorIndex || 0 }));
        if (key === ORDER_KEY) {
            // فارغة = "" لا "[]": هذه هي القيمة التي يحفظها أودو لطلب بلا
            // ملاحظة، فلا يظهر حذفها كتغيير وهمي ينتظر الإرسال.
            this.order.setInternalNote(clean.length ? JSON.stringify(clean) : "");
            return true;
        }
        const line = this.pos.models["pos.order.line"].getBy("uuid", key);
        if (!line || line.order_id?.uuid !== this.props.orderUuid) {
            return false;
        }
        line.setNote(JSON.stringify(clean));
        return true;
    }

    addNote(key, rawText, colorIndex = null) {
        const text = String(rawText || "")
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, HOSNY_NOTE_MAX_LENGTH);
        if (!text) {
            return;
        }
        const notes = this.notesOf(key);
        if (!notes) {
            return;
        }
        if (!notes.some((note) => sameText(note.text, text))) {
            notes.push({ text, colorIndex: colorIndex ?? this.colorFor(text) });
            this.writeNotes(key, notes);
        }
        this.state.drafts[key] = "";
    }

    removeNote(key, index) {
        const notes = this.notesOf(key);
        if (!notes || index < 0 || index >= notes.length) {
            return;
        }
        notes.splice(index, 1);
        this.writeNotes(key, notes);
    }

    commitDrafts() {
        for (const [key, text] of Object.entries(this.state.drafts)) {
            if (text && text.trim()) {
                this.addNote(key, text);
            }
        }
    }

    // ── الواجهة ──────────────────────────────────────────────────────────

    toggleEditor(line) {
        const current = this.state.editing;
        if (current && current !== ORDER_KEY && this.state.drafts[current]?.trim()) {
            this.addNote(current, this.state.drafts[current]);
        }
        this.state.editing = current === line.uuid ? null : line.uuid;
    }

    onDraftInput(key, ev) {
        this.state.drafts[key] = ev.target.value;
    }

    onDraftKeydown(key, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.addNote(key, this.state.drafts[key]);
        }
    }

    close({ commit = true } = {}) {
        if (this.closing) {
            return;
        }
        this.closing = true;
        if (commit) {
            this.commitDrafts();
        } else {
            this.state.drafts = {};
        }
        this.props.close();
    }

    async send() {
        if (!this.canSend(this.sendInfo(this.kitchen))) {
            return;
        }
        // النافذة تُغلق أولاً: الإرسال في المطعم ينتهي بخريطة الطاولات، ولا
        // يصح أن يتم تحتها. زر «إرسال الطلب» نفسه هو من ينفّذ، فحالة التحميل
        // التي تمنع «الدفع» أثناء الإرسال تبقى كما هي.
        const sendOrder = this.props.sendOrder;
        this.close();
        await sendOrder();
    }
}

patch(PosStore.prototype, {
    async afterProcessServerData() {
        const result = await super.afterProcessServerData(...arguments);
        // لا ننتظرها: خط بطيء لا يؤخّر فتح الكاشير، والنافذة تتحدّث وحدها.
        this.hosnyRefreshPosNotes();
        return result;
    },

    /**
     * «الملاحظات الجاهزة» (pos.note) من الخادم مع كل فتح للكاشير.
     *
     * أودو 19 لا يسأل الخادم عن بياناته حين تُفتح الصفحة على جلسة مفتوحة
     * مخزّنة في المتصفح (IndexedDB) — إلا عند الفتح من لوحة التحكم أو بجلسة
     * جديدة. فتعديل الملاحظات في الخلفية (تعريبها مثلاً، 2026-10-02) لا يصل
     * كاشيراً يكتفي بـ F5 مهما طال. الجدول أربعة أسطر، فنعيد قراءته كله:
     * يُحدَّث الموجود ويُضاف الجديد في الذاكرة وفي IndexedDB، ويُحذف ما لم
     * يعد على الخادم. نفس نطاق أودو: ملاحظات نقطة البيع إن حُدّدت، وإلا الكل.
     */
    async hosnyRefreshPosNotes() {
        if (this.data.network.offline || !this.models["pos.note"]) {
            return;
        }
        try {
            const configured = (this.config.note_ids || [])
                .map((note) => note?.id ?? note)
                .filter(Boolean);
            const domain = configured.length ? [["id", "in", configured]] : [];
            const fresh = await this.data.searchRead("pos.note", domain);
            if (!Array.isArray(fresh)) {
                return;
            }
            const keep = new Set(fresh.map((note) => note.id));
            const stale = this.models["pos.note"].filter((note) => !keep.has(note.id));
            if (stale.length) {
                const ids = stale.map((note) => note.id);
                stale.forEach((note) => note.delete());
                this.data.deleteRecordsInIndexedDB("pos.note", ids);
            }
        } catch (error) {
            console.warn("[Hosny] could not refresh the POS notes", error);
        }
    },
});

patch(ProductScreen.prototype, {
    setup() {
        super.setup(...arguments);
        useSubEnv({ hosnyOrderPanel: this });
    },
});

patch(OrderSummary.prototype, {
    setup() {
        super.setup(...arguments);
        this.hosnyDialog = useService("dialog");
    },

    openHosnyOrderExpand() {
        const order = this.currentOrder;
        if (!order || order.isEmpty()) {
            return;
        }
        const panel = this.env.hosnyOrderPanel;
        this.hosnyDialog.add(HosnyOrderExpandDialog, {
            orderUuid: order.uuid,
            isSending: panel ? () => panel.doSubmitOrder?.status === "loading" : undefined,
            sendOrder: panel ? () => panel.sendHosnyOrder() : undefined,
        });
    },
});
