{
    'name': 'Rayton: Генератор КП',
    'version': '17.0.1.0.0',
    'summary': 'Генерація комерційних пропозицій СЕС/УЗЕ прямо з sale.order → n8n → PDF у чаттері',
    'description': """
        Модуль додає кнопку "Сформувати КП" у форму продажної пропозиції (sale.order).
        Wizard збирає параметри СЕС або УЗЕ, виконує розрахунки (інвертори, панелі),
        надсилає вебхук на n8n → Google Apps Script генерує PDF → повертає назад в Odoo.
        PDF автоматично з'являється у чаттері sale.order.
    """,
    'category': 'Sales',
    'author': 'Rayton',
    'depends': ['sale', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
