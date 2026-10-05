/**
 * توجيه على مستوى الصنف: تبويب «الأصناف» + «مجموعات الوجبات» على الطابعة.
 *
 * أودو يوجّه بالمجموعة فقط. هنا نضيف قاعدة أدق لكل طابعة:
 *   يُطبع الصنف إذا (مجموعته مختارة أو الصنف نفسه مختار) وليس ضمن الاستثناءات.
 */
import { PosConfig } from "@point_of_sale/app/models/pos_config";
import { patch } from "@web/core/utils/patch";

export const idsOf = (value) =>
    (value || []).map((v) => (v && typeof v === "object" ? v.id : v));

patch(PosConfig.prototype, {
    /**
     * أودو يكتشف «تغيير في الطلب» فقط للأصناف التي مجموعتها ضمن مجموعات
     * الطابعات. فصنف مختار يدوياً ومجموعته غير موجّهة لن يُكتشف أصلاً، لذلك
     * نضيف مجموعات الأصناف المختارة هنا. الفلترة الفعلية لكل طابعة تتم بعد ذلك.
     */
    get printerCategories() {
        const set = super.printerCategories;
        const templates = this.models["product.template"];
        for (const relPrinter of this.models["pos.printer"].getAll()) {
            const raw = relPrinter.raw;
            for (const tmplId of idsOf(raw.product_ids)) {
                const tmpl = templates?.get?.(tmplId);
                for (const categId of idsOf(tmpl?.pos_categ_ids)) {
                    set.add(categId);
                }
            }
        }
        // التذكرة المجمّعة (الكنترول) تحتوي الطلب كله، ومنه أقسام لا طابعة
        // موصولة لها بعد (السلطات مثلاً). بدون هذا لا تُكتشف أصنافها كتغيير
        // فلا تظهر في المجمّعة. فلترة كل محطة لأصنافها لا تتغيّر.
        const hasBundled = (this.models["pos.printer.line"]?.getAll?.() || []).some(
            (line) => line.enabled && line.bundled
        );
        if (hasBundled) {
            for (const categ of this.models["pos.category"]?.getAll?.() || []) {
                set.add(categ.id);
            }
        }
        return set;
    },
});
