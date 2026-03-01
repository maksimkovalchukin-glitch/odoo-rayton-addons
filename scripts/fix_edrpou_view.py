"""
Fix stale ir_ui_view record that still references removed 'edrpou' field.
Run with:
  cd /var/odoo/2xqjwr7pzvj.cloudpepper.site
  sudo -u odoo venv/bin/python3 src/odoo-bin shell -c odoo.conf -d 2xqjwr7pzvj.cloudpepper.site \
      --no-http < extra-addons/scripts/fix_edrpou_view.py
"""
import json

new_arch = (
    '<xpath expr="//page[@name=\'internal_notes\']" position="before">'
    '<page string="Rayton" name="rayton_info">'
    '<group string="\u0406\u0434\u0435\u043d\u0442\u0438\u0444\u0456\u043a\u0430\u0446\u0456\u044f">'
    '<field name="kved_name" string="\u041a\u0412\u0415\u0414 (\u043d\u0430\u0437\u0432\u0430)"/>'
    '<field name="director_name" string="\u041a\u0435\u0440\u0456\u0432\u043d\u0438\u043a"/>'
    '<field name="resource_link" string="\u041f\u043e\u0441\u0438\u043b\u0430\u043d\u043d\u044f \u0437 \u0440\u0435\u0441\u0443\u0440\u0441\u0443" widget="url"/>'
    '</group>'
    '<group string="\u041a\u043b\u0430\u0441\u0438\u0444\u0456\u043a\u0430\u0446\u0456\u044f">'
    '<field name="client_status" string="\u0421\u0442\u0430\u0442\u0443\u0441 \u043a\u043b\u0456\u0454\u043d\u0442\u0430"/>'
    '<field name="lead_temp" string="\u0422\u0435\u043c\u043f\u0435\u0440\u0430\u0442\u0443\u0440\u0430 \u043b\u0456\u0434\u0430"/>'
    '<field name="partner_source" string="\u0414\u0436\u0435\u0440\u0435\u043b\u043e"/>'
    '</group>'
    '<group string="\u041f\u0440\u043e\u0454\u043a\u0442">'
    '<field name="consumption_mwh" string="\u0421\u043f\u043e\u0436\u0438\u0432\u0430\u043d\u043d\u044f, \u041c\u0412\u0442\u00b7\u0433\u043e\u0434/\u043c\u0456\u0441"/>'
    '<field name="uze_proposal" string="\u041f\u0440\u043e\u043f\u043e\u0437\u0438\u0446\u0456\u044f \u0423\u0417\u0415"/>'
    '</group>'
    '</page>'
    '</xpath>'
)

arch_json = json.dumps({'en_US': new_arch})

print('=== Fix: edrpou view ===')
env.cr.execute(
    "UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE name = 'res.partner.form.rayton'",
    [arch_json]
)
rows = env.cr.rowcount
env.cr.commit()
print(f'Оновлено {rows} view(s)')

# Clear Odoo asset/web cache so browser reloads
env.cr.execute(
    "UPDATE ir_attachment SET store_fname = NULL WHERE name LIKE '%%/web/assets%%'"
)
env.cr.commit()
print('Assets cache cleared.')
print('=== Done ===')
