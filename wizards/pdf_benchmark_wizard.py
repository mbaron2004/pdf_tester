import base64
import time

from markupsafe import Markup, escape

from odoo import _, fields, models
from odoo.exceptions import UserError


class PdfBenchmarkWizard(models.TransientModel):
    _name = 'pdf.benchmark.wizard'
    _description = 'PDF Benchmark Wizard'

    sale_order_ids = fields.Many2many(
        'sale.order',
        string='Sale Orders',
        required=True,
    )
    engine = fields.Selection(
        selection=[
            ('wkhtmltopdf', 'wkhtmltopdf'),
            ('paper_muncher', 'Paper Muncher'),
        ],
        string='PDF Engine',
        required=True,
        default='wkhtmltopdf',
    )
    force_pipe_mode = fields.Boolean(
        string='Force pipe mode (ignore report.url)',
        default=True,
        help='Temporarily unsets report.url so Paper Muncher serves assets via pipes instead of HTTP.',
    )
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('done', 'Done')],
        default='draft',
    )
    total_time = fields.Float(string='Total Time (s)', readonly=True, digits=(16, 3))
    pdf_count = fields.Integer(string='PDF Count', readonly=True)
    avg_time = fields.Float(string='Avg Time per PDF (s)', readonly=True, digits=(16, 3))
    result_html = fields.Html(string='Results', readonly=True, sanitize=False)
    attachment_ids = fields.Many2many('ir.attachment', string='Generated PDFs', readonly=True)

    def _engine_report_type(self):
        self.ensure_one()
        return {
            'wkhtmltopdf': 'qweb-pdf',
            'paper_muncher': 'qweb-pdf-paper-muncher',
        }[self.engine]

    def _engine_label(self):
        return dict(self._fields['engine'].selection)[self.engine]

    def action_generate_benchmark(self):
        self.ensure_one()
        if not self.sale_order_ids:
            raise UserError(_('Select at least one sale order.'))

        report = self.env.ref('sale.action_report_saleorder')
        original_report_type = report.report_type
        config_param = self.env['ir.config_parameter'].sudo()
        original_report_url = config_param.get_str('report.url')
        report_url_cleared = False

        if self.force_pipe_mode and original_report_url:
            config_param.set_str('report.url', '')
            report_url_cleared = True

        report.report_type = self._engine_report_type()

        pdf_lines = []
        attachment_vals = []
        errors = []
        start = time.perf_counter()

        try:
            for order in self.sale_order_ids:
                order_start = time.perf_counter()
                try:
                    pdf_content, _report_type = report._render_qweb_pdf(
                        report.id,
                        res_ids=[order.id],
                    )
                except Exception as exc:
                    errors.append(f'{order.display_name}: {exc}')
                    continue

                order_elapsed = time.perf_counter() - order_start
                filename = f'{order.name}.pdf'
                attachment_vals.append({
                    'name': filename,
                    'type': 'binary',
                    'datas': base64.b64encode(pdf_content),
                    'res_model': self._name,
                    'res_id': self.id,
                    'mimetype': 'application/pdf',
                })
                pdf_lines.append(
                    f'<li><b>{filename}</b> — {len(pdf_content):,} bytes — {order_elapsed:.3f}s</li>'
                )
        finally:
            report.report_type = original_report_type
            if report_url_cleared:
                config_param.set_str('report.url', original_report_url or '')

        elapsed = time.perf_counter() - start
        success_count = len(attachment_vals)
        attachments = self.env['ir.attachment'].create(attachment_vals) if attachment_vals else self.env['ir.attachment']

        error_block = ''
        if errors:
            error_block = (
                '<h4>Errors</h4><ul>'
                + ''.join(f'<li>{escape(err)}</li>' for err in errors)
                + '</ul>'
            )

        self.write({
            'state': 'done',
            'total_time': elapsed,
            'pdf_count': success_count,
            'avg_time': elapsed / success_count if success_count else 0.0,
            'attachment_ids': [(6, 0, attachments.ids)],
            'result_html': Markup(
                f'<h3>Benchmark Results</h3>'
                f'<ul>'
                f'<li><b>Engine:</b> {escape(self._engine_label())}</li>'
                f'<li><b>Report type:</b> {escape(self._engine_report_type())}</li>'
                f'<li><b>Pipe mode:</b> {"enabled (report.url cleared)" if report_url_cleared else "disabled"}</li>'
                f'<li><b>Total time:</b> {elapsed:.3f}s</li>'
                f'<li><b>PDF count:</b> {success_count} / {len(self.sale_order_ids)}</li>'
                f'<li><b>Avg per PDF:</b> {(elapsed / success_count if success_count else 0.0):.3f}s</li>'
                f'</ul>'
                f'<h4>Generated PDFs</h4>'
                f'<ul>{"".join(pdf_lines) if pdf_lines else "<li>No PDFs generated.</li>"}</ul>'
                f'{error_block}'
            ),
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('PDF Benchmark Results'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
