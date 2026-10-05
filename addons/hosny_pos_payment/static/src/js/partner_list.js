/** @odoo-module **/

/**
 * شاشة اختيار العميل بتقسيمة FERP وبالعربية فقط: بحث بالجوال / بالاسم /
 * بالكود، جدول مرقّم يُفتح فيه عنوان العميل، ولوحة جانبية للعميل المحدد.
 *
 * القالب جديد على الفئة نفسها (PartnerList.template)؛ منطق أودو وما أضافه
 * pos_modern_ui (المفضلة، حذف المكرر وعملاء التجربة) يبقى كما هو.
 * الضغط على صف يحدده في اللوحة، و«تأكيد» (أو الضغط المزدوج) يختاره للطلب.
 */
import { patch } from "@web/core/utils/patch";
import { debounce } from "@web/core/utils/timing";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

/** البحث في كل العملاء على السيرفر يبدأ من 4 خانات، كما في FERP. */
const SERVER_MIN = 4;

const MODES = {
    phone: { fields: ["phone_mobile_search"], label: "رقم الجوال" },
    name: { fields: ["complete_name"], label: "اسم العميل" },
    code: { fields: ["ref", "barcode"], label: "كود العميل" },
};

patch(PartnerList, {
    template: "hosny_pos_payment.PartnerList",
});

patch(PartnerList.prototype, {
    setup() {
        super.setup(...arguments);
        this.state.hpMode = "name";
        this.state.hpPicked = this.props.partner || null;
        this.state.hpExpanded = {};
        this.hpServerSearch = debounce(() => {
            if ((this.state.query || "").trim().length >= SERVER_MIN) {
                this.searchPartner();
            }
        }, 400);
    },

    // ── البحث ───────────────────────────────────────────────────────────
    hpValue(mode) {
        return this.state.hpMode === mode ? this.state.query : "";
    },
    hpType(mode, ev) {
        this.state.hpMode = mode;
        this.state.query = ev.target.value;
        this.hpServerSearch();
    },
    hpClear() {
        this.state.query = "";
    },
    get hpQueryShort() {
        const q = (this.state.query || "").trim();
        return q.length > 0 && q.length < SERVER_MIN;
    },
    _getSearchFields(query) {
        const mode = MODES[this.state.hpMode];
        return mode && this.state.hpMode !== "name" ? mode.fields : super._getSearchFields(query);
    },
    getPartners(partners) {
        const query = (this.state.query || "").trim();
        if (!query || this.state.hpMode === "name") {
            return super.getPartners(partners);
        }
        const lower = query.toLowerCase();
        const digits = query.replace(/\D/g, "");
        const match =
            this.state.hpMode === "phone"
                ? (p) => digits && [p.phone, p.mobile].some((v) => (v || "").replace(/\D/g, "").includes(digits))
                : (p) => [p.ref, p.barcode].some((v) => (v || "").toString().toLowerCase().includes(lower));
        const list = partners.filter(match).slice(0, 50);
        return this._hosnyDeduplicatePartners ? this._hosnyDeduplicatePartners(list) : list;
    },
    /** الأولية ثم المحمّلة من السيرفر، بلا تكرار، في جدول واحد. */
    get hpRows() {
        const seen = new Set();
        return [
            ...this.getPartners(this.state.initialPartners),
            ...this.getPartners(this.state.loadedPartners),
        ].filter((p) => !seen.has(p.id) && seen.add(p.id));
    },

    // ── الاختيار ────────────────────────────────────────────────────────
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
    get hpCanEdit() {
        return this.pos.cashier?._role !== "minimal";
    },
    hpPhone(partner) {
        return partner?.phone || partner?.mobile || "";
    },
});
