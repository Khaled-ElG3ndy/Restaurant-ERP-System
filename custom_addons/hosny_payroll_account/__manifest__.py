{
    "name": "ربط الرواتب بالمحاسبة - حسني",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Payroll",
    "summary": "إنشاء القيود المحاسبية لقسائم الرواتب عند الاعتماد",
    "author": "Hosny",
    "license": "LGPL-3",
    "depends": [
        "account",
        "analytic",
        "bi_hr_payroll",
        "hosny_hr_payroll_ar",
    ],
    "data": [
        "views/hr_salary_rule_views.xml",
        "views/hr_department_views.xml",
        "views/hr_work_location_views.xml",
        "views/hr_payslip_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
