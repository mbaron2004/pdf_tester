from odoo import _, fields, models
from odoo.exceptions import UserError


class CssTestPrintWizard(models.TransientModel):
    _name = 'css.test.print.wizard'
    _description = 'CSS Test Print Wizard'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        required=True,
        readonly=True,
    )
    template = fields.Selection(
        selection=[
            ('basic', 'Basic — tabla simple y texto centrado'),
            ('advanced', 'Advanced — flexbox, columnas y tabla estilizada'),
            ('extreme', 'Extreme — grid, gradientes, sombras y layout complejo'),
            ('ultraextreme', 'Ultraextreme — grid areas, transforms, tablas anidadas, filtros'),
        ],
        string='CSS Template',
        required=True,
        default='basic',
    )

    _REPORT_XMLIDS = {
        'basic': 'pdf_tester.action_report_css_test_basic',
        'advanced': 'pdf_tester.action_report_css_test_advanced',
        'extreme': 'pdf_tester.action_report_css_test_extreme',
        'ultraextreme': 'pdf_tester.action_report_css_test_ultraextreme',
    }

    def action_print_css_test(self):
        self.ensure_one()
        xmlid = self._REPORT_XMLIDS.get(self.template)
        if not xmlid:
            raise UserError(_('Unknown CSS template.'))
        report = self.env.ref(xmlid)
        return report.report_action(self.sale_order_id)
