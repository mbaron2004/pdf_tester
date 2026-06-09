{
    "name": "Pdf Tester",
    "summary": "Benchmark PDF generation: wkhtmltopdf vs Paper Muncher on sale orders",
    "version": "19.4.1.0",
    "category": 'Customization',
    "application": False,
    "installable": True,
    "depends": ['sale', 'base_report_paper_muncher'],
    "data": [
        'security/ir.model.access.csv',
        'report/css_test_templates.xml',
        'report/sale_quotation_professional.xml',
        'report/paper_muncher_issues_test.xml',
        'views/sale_order_views.xml',
        'views/pdf_benchmark_wizard_views.xml',
    ],
    'assets': {},
    'license': 'LGPL-3',
}
