from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_open_css_test_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imprimir test CSS',
            'res_model': 'css.test.print.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_sale_order_id': self.id},
        }
