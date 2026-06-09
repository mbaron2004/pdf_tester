# Part of pdf_tester. Run inside Odoo shell (env must exist).
#
# Usage on server:
#   odoo-bin shell -d YOUR_DATABASE --no-http \
#     < /var/opt/odoo/src/odoo/L4/pdf_tester/scripts/pdf_benchmark_batch.py
#
# Or from an interactive shell:
#   exec(open('/var/opt/odoo/src/odoo/L4/pdf_tester/scripts/pdf_benchmark_batch.py').read())

# --- Configuration ---
ORDER_COUNT = 100
LINES_PER_ORDER = 3
FORCE_PIPE_MODE = True
BATCH_MODE = 'per_order'  # 'per_order' or 'bulk'
RECREATE_ORDERS = False   # True: always create new orders; False: reuse existing benchmark orders
# ---------------------

Wizard = env['pdf.benchmark.wizard']

if RECREATE_ORDERS:
    print(f'Creating {ORDER_COUNT} benchmark sale orders...')
    orders = Wizard.create_benchmark_sale_orders(ORDER_COUNT, lines_per_order=LINES_PER_ORDER)
    env.cr.commit()
    print(f'Created {len(orders)} orders (origin={orders[:1].origin})')
else:
    orders = Wizard.get_benchmark_sale_orders(limit=ORDER_COUNT)
    if len(orders) < ORDER_COUNT:
        missing = ORDER_COUNT - len(orders)
        print(f'Found {len(orders)} existing benchmark orders, creating {missing} more...')
        orders |= Wizard.create_benchmark_sale_orders(missing, lines_per_order=LINES_PER_ORDER)
        env.cr.commit()
    print(f'Using {len(orders)} benchmark orders')

print(f'Running dual-engine benchmark (batch_mode={BATCH_MODE}, pipe_mode={FORCE_PIPE_MODE})...')
dual_result = Wizard.run_dual_engine_benchmark(
    orders.ids,
    force_pipe_mode=FORCE_PIPE_MODE,
    batch_mode=BATCH_MODE,
)
print(Wizard._format_benchmark_result_text(dual_result))
