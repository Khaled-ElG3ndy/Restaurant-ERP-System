/** @odoo-module **/

/**
 * فلاتر شاشة «الطلبات» (طلب 2026-10-10): التاريخ (اليوم / أمس / آخر 7 أيام /
 * هذا الشهر / مخصص)، الوردية، طريقة الدفع، النوع (محلي / سفري)، والموظف —
 * وطريقة الدفع ظاهرة على كل طلب، وملخص (العدد والإجمالي وكل طريقة دفع).
 *
 *   • الطلبات المفتوحة على الجهاز («نشط») تُفلتر هنا.
 *   • المدفوعة («مدفوع») تأتي من الخادم بنفس الشروط (_computeSyncedOrdersDomain)،
 *     وتُفلتر هنا أيضاً لأن الشاشة تحتفظ بكل ما جلبته من قبل.
 *   • طريقة دفع أو وردية سابقة تعني طلبات مدفوعة، فتتحول القائمة إلى «مدفوع»؛
 *     و«غير مدفوع» يرجعها إلى «نشط».
 *   • البحث «أي شيء» (الافتراضي): أثناء الكتابة، وكل كلمة لازم تظهر في أي حقل —
 *     رقم الطلب والإيصال والفاتورة، العميل وجواله، الطاولة، الأصناف، الموظف،
 *     النادل، الملاحظات، والمبلغ. الهمزات والتاء المربوطة والألف المقصورة سواء.
 */
import { onWillStart, useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { fuzzyLookup } from "@web/core/utils/search";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { SearchBar } from "@point_of_sale/app/screens/ticket_screen/search_bar/search_bar";

const { DateTime } = luxon;

const UNPAID = "unpaid";
const EMPTY_FILTERS = { date: "all", from: "", to: "", session: "", payment: "", type: "", user: "" };

export const HOSNY_DATE_PRESETS = [
    ["all", "كل التواريخ"],
    ["today", "اليوم"],
    ["yesterday", "أمس"],
    ["week", "آخر 7 أيام"],
    ["month", "هذا الشهر"],
    ["custom", "تاريخ مخصص"],
];

const ANY = "ANY";
const ANY_SERVER_FIELDS = [
    "pos_reference",
    "tracking_number",
    "floating_order_name",
    "account_move.name",
    "partner_id.complete_name",
    "partner_id.phone",
    "lines.full_product_name",
    "lines.note",
    "user_id.name",
    "employee_id.name",
    "hosny_waiter_name",
    "hosny_staff_meal_name",
    "general_customer_note",
    "hosny_invoice_note",
    "internal_note",
    "payment_ids.payment_method_id.name",
];
const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";

/** أحمد = احمد، مدينة = مدينه، مصطفى = مصطفي، والأرقام العربية = الإنجليزية. */
export function hosnyNormalize(text) {
    return String(text ?? "")
        .toLowerCase()
        .replace(/[\u064B-\u0652\u0640]/g, "")
        .replace(/[أإآ]/g, "ا")
        .replace(/ة/g, "ه")
        .replace(/ى/g, "ي")
        .replace(/[٠-٩]/g, (d) => String(AR_DIGITS.indexOf(d)));
}

function searchWords(term) {
    return String(term || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean);
}

/** صيغ الكلمة كما قد تُكتب في قاعدة البيانات (الخادم لا يوحّد الهمزات). */
function wordVariants(word) {
    const base = hosnyNormalize(word);
    const variants = new Set([word, base]);
    for (const form of [...variants]) {
        if (form.startsWith("ا")) {
            for (const alef of ["أ", "إ", "آ"]) {
                variants.add(alef + form.slice(1));
            }
        }
    }
    for (const form of [...variants]) {
        if (form.endsWith("ه")) {
            variants.add(form.slice(0, -1) + "ة");
        }
        if (form.endsWith("ي")) {
            variants.add(form.slice(0, -1) + "ى");
        }
    }
    return [...variants];
}

/** OR بين عناصر domain (صيغة أودو البادئة). */
function orDomain(items) {
    return items.length ? [...Array(items.length - 1).fill("|"), ...items] : [];
}

/** رقم السجل في حقل many2one حتى لو لم يُحمَّل السجل نفسه في الجهاز. */
function relId(record, field) {
    const value = record[field];
    if (value?.id) {
        return value.id;
    }
    const raw = record.raw?.[field];
    return Array.isArray(raw) ? raw[0] : raw || false;
}

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.hosnyDatePresets = HOSNY_DATE_PRESETS;
        this.hosnyFilters = useState({ ...EMPTY_FILTERS });
        this.hosnyOptions = useState({ sessions: [], payment_methods: [], order_types: [], users: [] });
        this.hosnySummary = useState({ loading: false, data: null });
        if (!this.props.stateOverride?.search && this.state.search.fieldName !== "PARTNER") {
            this.state.search = { ...this.state.search, fieldName: ANY };
        }
        onWillStart(() => this.hosnyLoadFilterOptions());
    },

    /* ── البحث بأي شيء ── */
    _getSearchFields() {
        return {
            [ANY]: {
                repr: (order) => this.hosnyHaystack(order),
                displayName: _t("أي شيء"),
                modelFields: ANY_SERVER_FIELDS,
            },
            ...super._getSearchFields(...arguments),
        };
    },

    get hosnyAnySearch() {
        return this.state.search.fieldName === ANY && Boolean(this.state.search.searchTerm?.trim());
    },

    /** كل ما يُبحث فيه عن الطلب، موحَّد الحروف. */
    hosnyHaystack(order) {
        const parts = [
            order.getName?.(),
            order.pos_reference,
            order.tracking_number,
            order.floating_order_name,
            order.invoiceName,
            order.partner_id?.name,
            order.partner_id?.phone,
            order.table_id?.table_number,
            order.table_id?.floor_id?.name,
            order.user_id?.name,
            order.employee_id?.name,
            order.hosny_waiter_name,
            order.hosny_staff_meal_name,
            order.general_customer_note,
            order.hosny_invoice_note,
            order.internal_note,
            order.priceIncl?.toFixed?.(2),
            this.pos.getDate?.(order.date_order),
            ...(order.payment_ids || []).map((p) => p.payment_method_id?.name),
            ...(order.lines || []).flatMap((line) => [line.getFullProductName?.(), line.note]),
        ];
        return hosnyNormalize(parts.filter((part) => part || part === 0).join(" "));
    },

    hosnyAnyMatches(order) {
        const haystack = this.hosnyHaystack(order);
        return searchWords(this.state.search.searchTerm).every((word) => haystack.includes(hosnyNormalize(word)));
    },

    /** كل كلمة: أي حقل يحتويها (أو المبلغ / رقم الطاولة لو كانت رقماً)، والكلمات معاً. */
    hosnyAnyServerDomain() {
        const domain = [];
        for (const word of searchWords(this.state.search.searchTerm)) {
            const items = [];
            for (const variant of wordVariants(word)) {
                for (const field of ANY_SERVER_FIELDS) {
                    items.push([field, "ilike", variant]);
                }
            }
            const number = Number(hosnyNormalize(word));
            if (Number.isFinite(number) && /^[0-9.]+$/.test(hosnyNormalize(word))) {
                items.push(["amount_total", "=", number]);
                if (Number.isInteger(number)) {
                    items.push(["table_id.table_number", "=", number]);
                }
            }
            domain.push(...orDomain(items));
        }
        return domain;
    },

    async hosnyLoadFilterOptions() {
        try {
            const options = await this.pos.data.call("pos.order", "hosny_order_filter_options", [
                this.pos.config.id,
            ]);
            Object.assign(this.hosnyOptions, options || {});
        } catch {
            // بلا اتصال: طرق الدفع وأنواع الطلب من بيانات الجهاز
            this.hosnyOptions.payment_methods = (this.pos.config.payment_method_ids || []).map((m) => ({
                id: m.id,
                name: m.name,
            }));
            this.hosnyOptions.order_types = (this.pos.models["pos.order.type"]?.getAll() || []).map((t) => ({
                id: t.id,
                name: t.name,
            }));
        }
    },

    /* ── الفلاتر ── */
    get hosnyHasFilters() {
        const f = this.hosnyFilters;
        return f.date !== "all" || Boolean(f.session || f.payment || f.type || f.user);
    },

    /** [من، إلى) بتوقيت الجهاز، وأي طرف قد يكون null. */
    hosnyDateRange() {
        const f = this.hosnyFilters;
        const today = DateTime.local().startOf("day");
        switch (f.date) {
            case "today":
                return [today, today.plus({ days: 1 })];
            case "yesterday":
                return [today.minus({ days: 1 }), today];
            case "week":
                return [today.minus({ days: 6 }), today.plus({ days: 1 })];
            case "month":
                return [today.startOf("month"), today.plus({ days: 1 })];
            case "custom": {
                const from = f.from ? DateTime.fromISO(f.from).startOf("day") : null;
                const to = f.to ? DateTime.fromISO(f.to).startOf("day").plus({ days: 1 }) : null;
                return [from, to];
            }
        }
        return [null, null];
    },

    hosnyServerDomain() {
        const f = this.hosnyFilters;
        const domain = [];
        const [from, to] = this.hosnyDateRange();
        const utc = (dt) => dt.toUTC().toFormat("yyyy-MM-dd HH:mm:ss", { numberingSystem: "latn" });
        if (from) {
            domain.push(["date_order", ">=", utc(from)]);
        }
        if (to) {
            domain.push(["date_order", "<", utc(to)]);
        }
        if (f.session) {
            domain.push(["session_id", "=", Number(f.session)]);
        }
        if (f.payment === UNPAID) {
            domain.push(["id", "=", 0]); // المدفوعة ليس فيها غير مدفوع
        } else if (f.payment) {
            domain.push(["payment_ids.payment_method_id", "=", Number(f.payment)]);
        }
        if (f.type) {
            domain.push(["order_type_id", "=", Number(f.type)]);
        }
        if (f.user) {
            domain.push(["user_id", "=", Number(f.user)]);
        }
        return domain;
    },

    hosnyMatches(order) {
        const f = this.hosnyFilters;
        const [from, to] = this.hosnyDateRange();
        if (from && order.date_order < from) {
            return false;
        }
        if (to && order.date_order >= to) {
            return false;
        }
        if (f.session && relId(order, "session_id") !== Number(f.session)) {
            return false;
        }
        if (f.payment === UNPAID) {
            if (this.hosnyPaymentRows(order).length) {
                return false;
            }
        } else if (f.payment) {
            const methodId = Number(f.payment);
            if (!(order.payment_ids || []).some((p) => p.payment_method_id?.id === methodId)) {
                return false;
            }
        }
        if (f.type && relId(order, "order_type_id") !== Number(f.type)) {
            return false;
        }
        if (f.user && relId(order, "user_id") !== Number(f.user)) {
            return false;
        }
        return true;
    },

    hosnySet(key, value) {
        this.hosnyFilters[key] = value;
        if (key === "date" && value !== "custom") {
            this.hosnyFilters.from = "";
            this.hosnyFilters.to = "";
        }
        return this.hosnyApply();
    },

    hosnyClear() {
        Object.assign(this.hosnyFilters, EMPTY_FILTERS);
        return this.hosnyApply();
    },

    hosnySessionIsCurrent(sessionId) {
        return Number(sessionId) === this.pos.session?.id;
    },

    async hosnyApply() {
        this.state.page = 1;
        const f = this.hosnyFilters;
        const wantsPaid =
            (f.payment && f.payment !== UNPAID) || (f.session && !this.hosnySessionIsCurrent(f.session));
        if (wantsPaid && this.state.filter !== "SYNCED") {
            await this.onFilterSelected("SYNCED");
            return;
        }
        if (f.payment === UNPAID && this.state.filter === "SYNCED") {
            await this.onFilterSelected("ACTIVE_ORDERS");
            return;
        }
        if (this.state.filter === "SYNCED") {
            this.pos.screenState.ticketSCreen.offsetByDomain = {};
            await this._fetchSyncedOrders();
        }
        await this.hosnyRefreshSummary();
    },

    /* ── ربط الفلاتر بالشاشة ── */
    _computeSyncedOrdersDomain() {
        const search = this.state.search.fieldName === ANY ? this.hosnyAnyServerDomain() : super._computeSyncedOrdersDomain(...arguments);
        return [...search, ...this.hosnyServerDomain()];
    },

    async onFilterSelected() {
        await super.onFilterSelected(...arguments);
        await this.hosnyRefreshSummary();
    },

    async onSearch() {
        await super.onSearch(...arguments);
        await this.hosnyRefreshSummary();
    },

    /** كل الطلبات المطابقة (بلا تقسيم صفحات) — نفس خطوات أودو مع فلاترنا. */
    hosnyCollectOrders() {
        const synced = this.state.filter === "SYNCED";
        let orders = this.pos.models["pos.order"].filter(
            (o) => (synced ? o.finalized && o.uiState.displayed : this.activeOrderFilter(o)) && this.hosnyMatches(o)
        );
        if (this.state.filter && !["ACTIVE_ORDERS", "SYNCED"].includes(this.state.filter)) {
            orders = orders.filter(
                (order) => this._getScreenToStatusMap()[order.getScreenData().name] === this.state.filter
            );
        }
        if (this.hosnyAnySearch) {
            orders = orders.filter((order) => this.hosnyAnyMatches(order));
        } else if (this.state.search.searchTerm) {
            const repr = this._getSearchFields()[this.state.search.fieldName].repr;
            orders = fuzzyLookup(this.state.search.searchTerm, orders, repr);
        }
        if (this.state.search.partnerId && this.state.search.fieldName === "PARTNER") {
            orders = orders.filter((order) => order.partner_id?.id === this.state.search.partnerId);
        }
        if (this.state.selectedPreset) {
            orders = orders.filter((order) => order.preset_id?.id === this.state.selectedPreset.id);
        }
        const ascending = !synced;
        return orders.sort((a, b) => {
            if (!a.date_order.equals(b.date_order)) {
                return ascending ? a.date_order - b.date_order : b.date_order - a.date_order;
            }
            const nameA = parseInt(a.pos_reference.replace(/\D/g, "")) || 0;
            const nameB = parseInt(b.pos_reference.replace(/\D/g, "")) || 0;
            return ascending ? nameA - nameB : nameB - nameA;
        });
    },

    getFilteredOrderList() {
        if (!this.hosnyHasFilters && !this.hosnyAnySearch) {
            return super.getFilteredOrderList(...arguments);
        }
        const orders = this.hosnyCollectOrders();
        if (this.state.filter !== "SYNCED") {
            this.pos.screenState.ticketSCreen.totalCount = orders.length;
        }
        return orders.slice((this.state.page - 1) * this.state.nbrByPage, this.state.page * this.state.nbrByPage);
    },

    /* ── الملخص ── */
    async hosnyRefreshSummary() {
        if (this.state.filter !== "SYNCED") {
            this.hosnySummary.data = null; // المفتوحة تُحسب من الجهاز (hosnySummaryView)
            return;
        }
        // بحث أقدم (الأبطأ غالباً: بلا فلتر) قد يرجع بعد الأحدث: لا يكتب فوقه
        const seq = (this._hosnySummarySeq = (this._hosnySummarySeq || 0) + 1);
        this.hosnySummary.loading = true;
        let data = null;
        try {
            data = await this.pos.data.call("pos.order", "hosny_order_summary", [
                this.pos.config.id,
                this._computeSyncedOrdersDomain(),
            ]);
        } catch {
            data = null;
        }
        if (seq === this._hosnySummarySeq) {
            this.hosnySummary.data = data;
            this.hosnySummary.loading = false;
        }
    },

    get hosnySummaryView() {
        const money = (amount) => this.env.utils.formatCurrency(amount || 0);
        if (this.state.filter === "SYNCED") {
            const data = this.hosnySummary.data;
            if (!data) {
                return null;
            }
            return {
                count: data.count,
                total: money(data.total),
                methods: data.methods.map((m) => ({ key: m.id, name: m.name, amount: money(m.amount) })),
            };
        }
        const orders = this.hosnyCollectOrders();
        const methods = new Map();
        let total = 0;
        for (const order of orders) {
            total += order.priceIncl || 0;
            for (const row of this.hosnyPaymentRows(order)) {
                const entry = methods.get(row.key) || { key: row.key, name: row.name, amount: 0 };
                entry.amount += row.amount;
                methods.set(row.key, entry);
            }
        }
        return {
            count: orders.length,
            total: money(total),
            methods: [...methods.values()].map((m) => ({ ...m, amount: money(m.amount) })),
        };
    },

    /* ── طريقة الدفع على كل طلب ── */
    /** الدفعات مجمّعة لكل طريقة (الباقي مخصوم من النقدي). */
    hosnyPaymentRows(order) {
        const rows = new Map();
        for (const payment of order.payment_ids || []) {
            const method = payment.payment_method_id;
            const key = method?.id || 0;
            const row = rows.get(key) || {
                key,
                name: method?.name || _t("دفع"),
                tone: method?.type === "cash" ? "cash" : method?.type === "pay_later" ? "later" : "bank",
                amount: 0,
            };
            row.amount += payment.amount || 0;
            rows.set(key, row);
        }
        return [...rows.values()].filter((row) => Math.abs(row.amount) > 0.0001);
    },

    hosnyPaymentChips(order) {
        const rows = this.hosnyPaymentRows(order);
        if (!rows.length) {
            return [{ key: "none", name: order.finalized ? "—" : _t("غير مدفوع"), tone: "none", amount: "" }];
        }
        return rows.map((row) => ({
            ...row,
            amount: rows.length > 1 ? this.env.utils.formatCurrency(row.amount) : "",
        }));
    },

    hosnySessionLabel(session) {
        const number = (session.name || "").split("/").pop();
        const start = session.start_at
            ? DateTime.fromSQL(session.start_at, { zone: "utc" })
                  .setZone("local")
                  .toFormat("dd/MM HH:mm", { numberingSystem: "latn" })
            : "";
        const current = session.opened ? ` — ${_t("الحالية")}` : "";
        return `${_t("وردية")} ${number}${start ? ` · ${start}` : ""}${current}`;
    },
});

/**
 * «أي شيء» يبحث أثناء الكتابة (بعد توقف قصير)، وبلا قائمة اختيار الحقل.
 * نسمع «input» لا keyup: لوحات مفاتيح أندرويد العربية تكتب بلا أحداث مفاتيح عادية.
 */
patch(SearchBar.prototype, {
    hosnyAnySelected() {
        return (
            this.props.config.searchFields.has?.(ANY) &&
            this.searchFieldsList[this.state.selectedSearchFieldId] === ANY
        );
    },

    onHosnyInput() {
        if (!this.hosnyAnySelected()) {
            return;
        }
        clearTimeout(this._hosnySearchTimer);
        this.state.showSearchFields = false;
        this._hosnySearchTimer = setTimeout(() => this._onClickSearchField(ANY), this.state.searchInput ? 350 : 0);
    },

    onSearchInputKeyup(event) {
        if (!this.hosnyAnySelected() || ["ArrowUp", "ArrowDown"].includes(event.key)) {
            return super.onSearchInputKeyup(...arguments);
        }
        if (event.key === "Enter") {
            clearTimeout(this._hosnySearchTimer);
            this._onClickSearchField(ANY);
        }
    },
});
