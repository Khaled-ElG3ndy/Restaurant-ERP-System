from odoo import models


class IrHttp(models.AbstractModel):

    _inherit = "ir.http"

    #----------------------------------------------------------
    # Functions
    #----------------------------------------------------------
    
    def session_info(self):
        result = super(IrHttp, self).session_info()
        if self.env.user._is_internal():
            allowed_companies = result.get('user_companies', {}).get('allowed_companies', {})
            for company in self.env.user.company_ids.with_context(bin_size=True):
                company_info = allowed_companies.get(company.id)
                if company_info is not None:
                    company_info.update({
                        'has_appsbar_image': bool(company.appbar_image),
                    })
        return result
