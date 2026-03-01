"""
Очищення кешу ir.ui.view в Odoo без рестарту сервера.
"""
print('=== Clear view cache ===')

# Очищаємо registry cache (зберігає скомпільовані view)
env.registry.clear_cache()
print('Registry cache cleared.')

# Інвалідуємо recordset cache для ir.ui.view
env['ir.ui.view'].clear_caches()
print('View caches cleared.')

# Перевіряємо що наш view вже без edrpou
env.cr.execute("SELECT arch_db::text FROM ir_ui_view WHERE name = 'res.partner.form.rayton'")
row = env.cr.fetchone()
has_edrpou = 'edrpou' in (row[0] if row else '')
print(f'View has edrpou: {has_edrpou}')

print('=== Done ===')
