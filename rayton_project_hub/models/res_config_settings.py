from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    tg_bot_token = fields.Char(
        string='Telegram Bot Token',
        config_parameter='rayton_project_hub.tg_bot_token',
        help='Токен Telegram бота для надсилання повідомлень у групи проектів',
    )
