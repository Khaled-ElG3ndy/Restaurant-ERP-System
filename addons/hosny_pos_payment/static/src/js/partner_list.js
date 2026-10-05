/** @odoo-module **/

/**
 * شاشة اختيار العميل بتقسيمة FERP وبالعربية فقط.
 *
 * لا تُعرض قائمة العملاء كلها: الجدول فارغ حتى يُكتب في خانة البحث. البحث
 * «ذكي»: أرقام ← رقم الجوال (بـ 966 أو بالصفر أو بدونهما) أو الكود، وحروف ←
 * الاسم (مع توحيد أ/إ/آ وة/ه وى/ي) أو الكود. يُصفّى ما هو محمّل فوراً، ومن 3
 * خانات يُسأل السيرفر أيضاً. الأسهم تتنقل بين النتائج و Enter يختار المحدد.
 *
 * القالب جديد على الفئة نفسها (PartnerList.template)؛ منطق أودو وما أضافه
 * pos_modern_ui (المفضلة، حذف المكرر وعملاء التجربة) يبقى كما هو.
 */
import { patch } from "@web/core/utils/patch";
import { debounce } from "@web/core/utils/timing";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

const SERVER_MIN = 3;
const MAX_ROWS = 30;

/** توحيد الحروف العربية للمقارنة. */
function fold(text) {
    return String(text || "")
        .toLowerCase()
        .replace(/[ً-ْـ]/g, "")
        .replace(/[أإآ]/g, "ا")
        .replace(/ة/g, "ه")
        .replace(/ى/g, "ي")
        .replace(/\s+/g, " ")
        .trim();
}

/** أرقام الجوال بصيغها: 9665xxxxxxxx و 05xxxxxxxx و 5xxxxxxxx تتطابق. */
function phoneForms(value) {
    const digits = String(value || "").replace(/\D/g, "");
    if (!digits) {
        return [];
    }
    const local = digits.replace(/^00966|^966/, "").replace(/^0+/, "");
    return [digits, local, "0" + local];
}

patch(PartnerList, {
    template: "hosny_pos_payment.PartnerList",
});

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.hpPicked = this.props.partner || null;
        this.state.hpExpanded = {};
        this.hpServerSearch = debounce(() => {
            if (this.hpQuery.length >= SERVER_MIN) {
                this.searchPartner();
            }
        }, 350);
    },

    // ── البحث ───────────────────────────────────────────────────────────
    get hpQuery() {
        return (this.state.query || "").trim();
    },
    get hpIsNumber() {
        return /^[\d\s+()-]+$/.test(this.hpQuery);
    },
    hpType(ev) {
        this.state.query = ev.target.value;
        this.state.hpPicked = null;
        this.hpServerSearch();
    },
    hpClear() {
        this.state.query = "";
        this.state.hpPicked = null;
    },
    /** حقول بحث السيرفر حسب نوع ما كُتب. */
    _getSearchFields(query) {
        return this.hpIsNumber ? ["phone_mobile_search", "ref", "barcode"] : ["complete_name", "ref", "barcode"];
    },
    /** رقم يبدأ بصفر يُبحث عنه أيضاً بلا صفر، ليطابق الأرقام المحفوظة بـ 966. */
    async getNewPartners() {
        const query = this.hpQuery;
        const result = await super.getNewPartners(...arguments);
        if (this.hpIsNumber && /^0\d{3,}/.test(query.replace(/\D/g, ""))) {
            const saved = this.state.query;
            this.state.query = query.replace(/\D/g, "").replace(/^0+/, "");
            try {
                await super.getNewPartners(...arguments);
            } finally {
                this.state.query = saved;
            }
        }
        return result;
    },
    /** درجة التطابق: 3 بداية، 2 كلمة تبدأ به، 1 يحتويه، 0 لا تطابق. */
    hpScore(partner) {
        const query = this.hpQuery;
        if (this.hpIsNumber) {
            const q = query.replace(/\D/g, "");
            const qForms = phoneForms(q).filter((f) => f.length >= Math.min(3, q.length));
            let best = 0;
            for (const value of [partner.phone, partner.mobile]) {
                for (const form of phoneForms(value)) {
                    for (const qf of qForms) {
                        if (form.startsWith(qf)) {
                            best = Math.max(best, 3);
                        } else if (form.includes(qf)) {
                            best = Math.max(best, 1);
                        }
                    }
                }
            }
            for (const code of [partner.ref, partner.barcode]) {
                if (code && String(code).includes(q)) {
                    best = Math.max(best, 2);
                }
            }
            return best;
        }
        const q = fold(query);
        const name = fold(partner.name);
        let best = name.startsWith(q) ? 3 : name.split(" ").some((w) => w.startsWith(q)) ? 2 : name.includes(q) ? 1 : 0;
        for (const code of [partner.ref, partner.barcode]) {
            if (code && fold(code).includes(q)) {
                best = Math.max(best, 2);
            }
        }
        return best;
    },
    /** النتائج فقط — لا شيء قبل الكتابة — الأقرب أولاً. */
    get hpMatches() {
        if (!this.hpQuery) {
            return [];
        }
        const seen = new Set();
        let rows = [...this.state.initialPartners, ...this.state.loadedPartners]
            .filter((p) => !seen.has(p.id) && seen.add(p.id))
            .map((partner) => ({ partner, score: this.hpScore(partner) }))
            .filter((r) => r.score > 0)
            .sort((a, b) => b.score - a.score || (a.partner.name || "").localeCompare(b.partner.name || "", "ar", { numeric: true }))
            .map((r) => r.partner);
        if (this._hosnyDeduplicatePartners) {
            rows = this._hosnyDeduplicatePartners(rows);
        }
        return rows;
    },
    get hpRows() {
        return this.hpMatches.slice(0, MAX_ROWS);
    },
    get hpMoreCount() {
        return Math.max(0, this.hpMatches.length - MAX_ROWS);
    },
    /** التحميل عند التمرير لأسفل فقط أثناء البحث. */
    onScroll() {
        if (this.hpQuery.length >= SERVER_MIN) {
            return super.onScroll(...arguments);
        }
    },
    get hpShortQuery() {
        return this.hpQuery.length > 0 && this.hpQuery.length < SERVER_MIN;
    },

    // ── الاختيار ولوحة المفاتيح ─────────────────────────────────────────
    hpPick(partner) {
        this.state.hpPicked = partner;
    },
    hpIsPicked(partner) {
        return this.state.hpPicked?.id === partner.id;
    },
    hpToggle(partner) {
        this.state.hpExpanded[partner.id] = !this.state.hpExpanded[partner.id];
    },
    hpConfirm() {
        if (this.state.hpPicked) {
            this.clickPartner(this.state.hpPicked);
        }
    },
    /** الأسهم تنقل التحديد بين النتائج. */
    hpKeydown(ev) {
        if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") {
            return;
        }
        const rows = this.hpRows;
        if (!rows.length) {
            return;
        }
        ev.preventDefault();
        const index = rows.findIndex((p) => p.id === this.state.hpPicked?.id);
        const next = ev.key === "ArrowDown" ? Math.min(rows.length - 1, index + 1) : Math.max(0, index - 1);
        this.state.hpPicked = rows[next];
    },
    /** Enter: يختار المحدد، أو أول نتيجة، وإلا يبحث على السيرفر. */
    async onEnter() {
        const rows = this.hpRows;
        const picked = rows.find((p) => p.id === this.state.hpPicked?.id) || (rows.length === 1 ? rows[0] : null);
        if (picked) {
            this.clickPartner(picked);
            return;
        }
        if (this.hpQuery) {
            await this.searchPartner();
        }
    },
    get hpCanEdit() {
        return this.pos.cashier?._role !== "minimal";
    },
    hpPhone(partner) {
        return partner?.phone || partner?.mobile || "";
    },
});
