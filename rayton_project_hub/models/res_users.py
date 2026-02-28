from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    tg_user_id = fields.Char(
        string='Telegram User ID',
        help='Числовий ID користувача в Telegram (не username). '
             'Отримати можна через бота @userinfobot — надішліть йому /start.',
    )

    def _register_hook(self):
        """
        Ensure the tg_user_id column exists in the DB on every server start.

        Odoo calls _register_hook() whenever the model registry is rebuilt
        (startup, upgrade, etc.). Using ALTER TABLE ... ADD COLUMN IF NOT EXISTS
        is idempotent — it's a no-op if the column already exists.

        This avoids the circular dependency where:
          new code (field in Python) → server 500 → can't trigger upgrade → column never created
        """
        self.env.cr.execute(
            "ALTER TABLE res_users ADD COLUMN IF NOT EXISTS tg_user_id varchar;"
        )
        return super()._register_hook()
