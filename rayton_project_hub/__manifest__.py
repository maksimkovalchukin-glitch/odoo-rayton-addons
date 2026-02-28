{
    'name': 'Rayton: Ініціація проекту + Discuss Чат',
    'version': '17.0.1.0.0',
    'summary': 'Ініціація проекту з CRM нагоди, автоматичне прив\'язування Discuss каналу та бокова чат-панель у задачах проекту',
    'description': """
        Єдиний модуль який:
        1. Додає кнопку "Ініціювати проект" у CRM нагоду
        2. Відкриває wizard з вибором шаблону (СЕС / УЗЕ / СЕС+УЗЕ)
        3. Створює проект з шаблону з назвою як в угоді
        4. Створює канал Discuss з тією ж назвою і прив'язує до проекту
        5. Надсилає вебхук на n8n з даними: ініціатор, id каналу, id проекту
        6. Показує бокову чат-панель у списку задач проекту (десктоп + мобільний)
    """,
    'category': 'Project',
    'author': 'Rayton',
    'depends': ['crm', 'project', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/telegram_chat_views.xml',
        'views/res_config_settings_views.xml',
        'views/crm_lead_views.xml',
        'views/project_views.xml',
        'wizard/project_initiate_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'rayton_project_hub/static/src/css/discussion_panel.css',
            'rayton_project_hub/static/src/xml/discussion_panel.xml',
            'rayton_project_hub/static/src/js/discussion_panel.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
