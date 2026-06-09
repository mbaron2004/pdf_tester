from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_print_css_test_extreme(self):
        self.ensure_one()
        report = self.env.ref('pdf_tester.action_report_css_test_extreme')
        return report.report_action(self)
