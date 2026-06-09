from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_print_css_test_extreme(self):
        self.ensure_one()
        report = self.env.ref('pdf_tester.action_report_css_test_extreme')
        return report.report_action(self)

    def action_print_professional_quotation(self):
        self.ensure_one()
        report = self.env.ref('pdf_tester.action_report_sale_quotation_professional')
        return report.report_action(self)

    def action_print_pm_issues_test_wkhtml(self):
        self.ensure_one()
        report = self.env.ref('pdf_tester.action_report_paper_muncher_issues_test')
        return report.report_action(self)

    def action_print_pm_issues_test_paper_muncher(self):
        self.ensure_one()
        report = self.env.ref('pdf_tester.action_report_paper_muncher_issues_test_pm')
        return report.report_action(self)
