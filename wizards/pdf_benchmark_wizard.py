import base64
import time

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

BENCHMARK_PARTNER_NAME = 'PDF Benchmark Customer'
BENCHMARK_PRODUCT_NAME = 'PDF Benchmark Product'
BENCHMARK_ORIGIN = 'pdf_tester_benchmark'


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

    # -------------------------------------------------------------------------
    # Engine helpers
    # -------------------------------------------------------------------------

    @api.model
    def _engine_report_type_map(self):
        return {
            'wkhtmltopdf': 'qweb-pdf',
            'paper_muncher': 'qweb-pdf-paper-muncher',
        }

    def _engine_report_type(self):
        self.ensure_one()
        return self._engine_report_type_map()[self.engine]

    def _engine_label(self):
        return dict(self._fields['engine'].selection)[self.engine]

    # -------------------------------------------------------------------------
    # Test data generation (callable from shell script)
    # -------------------------------------------------------------------------

    @api.model
    def _get_or_create_benchmark_partner(self):
        partner = self.env['res.partner'].search(
            [('name', '=', BENCHMARK_PARTNER_NAME)], limit=1,
        )
        if not partner:
            partner = self.env['res.partner'].create({'name': BENCHMARK_PARTNER_NAME})
        return partner

    @api.model
    def _get_or_create_benchmark_product(self):
        product = self.env['product.product'].search(
            [('name', '=', BENCHMARK_PRODUCT_NAME)], limit=1,
        )
        if product:
            return product
        product = self.env['product.product'].search([('sale_ok', '=', True)], limit=1)
        if product:
            return product
        return self.env['product.product'].create({
            'name': BENCHMARK_PRODUCT_NAME,
            'type': 'service',
            'list_price': 42.0,
            'sale_ok': True,
        })

    @api.model
    def create_benchmark_sale_orders(self, count=100, lines_per_order=3):
        """Create *count* sale orders tagged for PDF benchmarking."""
        partner = self._get_or_create_benchmark_partner()
        product = self._get_or_create_benchmark_product()
        orders = self.env['sale.order']

        vals_list = []
        for i in range(count):
            vals_list.append({
                'partner_id': partner.id,
                'origin': BENCHMARK_ORIGIN,
                'note': f'Auto-generated for pdf_tester benchmark #{i + 1}',
                'order_line': [
                    (0, 0, {
                        'product_id': product.id,
                        'product_uom_qty': (i % 5) + 1,
                    })
                    for _ in range(lines_per_order)
                ],
            })

        created = orders.create(vals_list)
        return created

    @api.model
    def get_benchmark_sale_orders(self, limit=100):
        """Return existing benchmark orders (newest first)."""
        return self.env['sale.order'].search(
            [('origin', '=', BENCHMARK_ORIGIN)],
            order='id desc',
            limit=limit,
        )

    # -------------------------------------------------------------------------
    # Benchmark core (callable from UI and shell)
    # -------------------------------------------------------------------------

    @api.model
    def run_engine_benchmark(
        self,
        sale_order_ids,
        engine,
        force_pipe_mode=True,
        batch_mode='per_order',
        save_pdfs=False,
        attachment_res_id=None,
    ):
        """
        Run PDF benchmark for the given engine.

        :param sale_order_ids: recordset or list of sale.order ids
        :param engine: 'wkhtmltopdf' or 'paper_muncher'
        :param force_pipe_mode: temporarily clear report.url
        :param batch_mode: 'per_order' (loop) or 'bulk' (single render call)
        :param save_pdfs: store generated PDFs as ir.attachment on this model
        :returns: dict with timing stats
        """
        report_type_map = self._engine_report_type_map()
        if engine not in report_type_map:
            raise UserError(_('Unknown engine: %s') % engine)

        orders = self.env['sale.order'].browse(sale_order_ids)
        if not orders:
            raise UserError(_('No sale orders provided.'))

        report = self.env.ref('sale.action_report_saleorder')
        original_report_type = report.report_type
        config_param = self.env['ir.config_parameter'].sudo()
        original_report_url = config_param.get_str('report.url')
        report_url_cleared = False

        if force_pipe_mode and original_report_url:
            config_param.set_str('report.url', '')
            report_url_cleared = True

        report.report_type = report_type_map[engine]

        per_order_times = []
        pdf_sizes = []
        errors = []
        pdf_contents = []
        start = time.perf_counter()

        try:
            if batch_mode == 'bulk':
                try:
                    pdf_content, _report_type = report._render_qweb_pdf(
                        report.id,
                        res_ids=orders.ids,
                    )
                    elapsed_bulk = time.perf_counter() - start
                    pdf_sizes.append(len(pdf_content))
                    pdf_contents.append((f'bulk_{len(orders)}_orders.pdf', pdf_content))
                    per_order_times.append(elapsed_bulk / len(orders))
                except Exception as exc:
                    errors.append(f'bulk render: {exc}')
            else:
                for order in orders:
                    order_start = time.perf_counter()
                    try:
                        pdf_content, _report_type = report._render_qweb_pdf(
                            report.id,
                            res_ids=[order.id],
                        )
                        order_elapsed = time.perf_counter() - order_start
                        per_order_times.append(order_elapsed)
                        pdf_sizes.append(len(pdf_content))
                        pdf_contents.append((f'{order.name}.pdf', pdf_content))
                    except Exception as exc:
                        errors.append(f'{order.display_name}: {exc}')
        finally:
            report.report_type = original_report_type
            if report_url_cleared:
                config_param.set_str('report.url', original_report_url or '')

        total_time = time.perf_counter() - start
        success_count = len(per_order_times)

        if save_pdfs and pdf_contents:
            attachment_vals = [{
                'name': filename,
                'type': 'binary',
                'datas': base64.b64encode(content),
                'res_model': self._name,
                'res_id': attachment_res_id or 0,
                'mimetype': 'application/pdf',
            } for filename, content in pdf_contents]
            self.env['ir.attachment'].create(attachment_vals)

        return {
            'engine': engine,
            'report_type': report_type_map[engine],
            'pipe_mode': report_url_cleared,
            'batch_mode': batch_mode,
            'total_time': total_time,
            'pdf_count': success_count,
            'order_count': len(orders),
            'avg_time': total_time / success_count if success_count else 0.0,
            'per_order_times': per_order_times,
            'total_bytes': sum(pdf_sizes),
            'avg_bytes': sum(pdf_sizes) / len(pdf_sizes) if pdf_sizes else 0,
            'errors': errors,
        }

    @api.model
    def run_dual_engine_benchmark(
        self,
        sale_order_ids,
        force_pipe_mode=True,
        batch_mode='per_order',
    ):
        """Run wkhtmltopdf and paper_muncher on the same orders and compare."""
        results = {}
        for engine in ('wkhtmltopdf', 'paper_muncher'):
            results[engine] = self.run_engine_benchmark(
                sale_order_ids,
                engine,
                force_pipe_mode=force_pipe_mode,
                batch_mode=batch_mode,
            )
        wk = results['wkhtmltopdf']
        pm = results['paper_muncher']
        speedup = (
            wk['total_time'] / pm['total_time']
            if pm['total_time'] else 0.0
        )
        return {
            'results': results,
            'comparison': {
                'wkhtmltopdf_total': wk['total_time'],
                'paper_muncher_total': pm['total_time'],
                'speedup_factor': speedup,
                'faster_engine': (
                    'paper_muncher' if pm['total_time'] < wk['total_time']
                    else 'wkhtmltopdf'
                ),
            },
        }

    @api.model
    def _format_benchmark_result_text(self, dual_result):
        cmp_ = dual_result['comparison']
        lines = [
            '=' * 60,
            'PDF BENCHMARK COMPARISON',
            '=' * 60,
        ]
        for engine, data in dual_result['results'].items():
            lines += [
                f'\n--- {engine} ---',
                f"  report_type : {data['report_type']}",
                f"  batch_mode  : {data['batch_mode']}",
                f"  pipe_mode   : {data['pipe_mode']}",
                f"  total_time  : {data['total_time']:.3f}s",
                f"  pdf_count   : {data['pdf_count']} / {data['order_count']}",
                f"  avg_time    : {data['avg_time']:.3f}s",
                f"  total_bytes : {data['total_bytes']:,}",
            ]
            if data['errors']:
                lines.append(f"  errors      : {len(data['errors'])}")
                for err in data['errors'][:5]:
                    lines.append(f'    - {err}')
        lines += [
            '\n--- comparison ---',
            f"  wkhtmltopdf   : {cmp_['wkhtmltopdf_total']:.3f}s",
            f"  paper_muncher : {cmp_['paper_muncher_total']:.3f}s",
            f"  faster        : {cmp_['faster_engine']}",
            f"  speedup       : {cmp_['speedup_factor']:.2f}x",
            '=' * 60,
        ]
        return '\n'.join(lines)

    # -------------------------------------------------------------------------
    # UI action
    # -------------------------------------------------------------------------

    def action_generate_benchmark(self):
        self.ensure_one()
        if not self.sale_order_ids:
            raise UserError(_('Select at least one sale order.'))

        result = self.run_engine_benchmark(
            self.sale_order_ids.ids,
            self.engine,
            force_pipe_mode=self.force_pipe_mode,
            batch_mode='per_order',
            save_pdfs=True,
            attachment_res_id=self.id,
        )

        pdf_lines = [
            f'<li><b>{self.sale_order_ids[i].name}.pdf</b> — {result["per_order_times"][i]:.3f}s</li>'
            for i in range(min(len(result['per_order_times']), len(self.sale_order_ids)))
        ]

        error_block = ''
        if result['errors']:
            error_block = (
                '<h4>Errors</h4><ul>'
                + ''.join(f'<li>{escape(err)}</li>' for err in result['errors'])
                + '</ul>'
            )

        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
        ], order='id desc', limit=result['pdf_count'])

        self.write({
            'state': 'done',
            'total_time': result['total_time'],
            'pdf_count': result['pdf_count'],
            'avg_time': result['avg_time'],
            'attachment_ids': [(6, 0, attachments.ids)],
            'result_html': Markup(
                f'<h3>Benchmark Results</h3>'
                f'<ul>'
                f'<li><b>Engine:</b> {escape(self._engine_label())}</li>'
                f'<li><b>Report type:</b> {escape(result["report_type"])}</li>'
                f'<li><b>Pipe mode:</b> {"enabled (report.url cleared)" if result["pipe_mode"] else "disabled"}</li>'
                f'<li><b>Total time:</b> {result["total_time"]:.3f}s</li>'
                f'<li><b>PDF count:</b> {result["pdf_count"]} / {result["order_count"]}</li>'
                f'<li><b>Avg per PDF:</b> {result["avg_time"]:.3f}s</li>'
                f'<li><b>Total bytes:</b> {result["total_bytes"]:,}</li>'
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
