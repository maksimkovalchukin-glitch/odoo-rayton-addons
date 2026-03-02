"""
Pipedrive → Odoo webhook синхронізація.

Endpoint: POST /pipedrive/webhook
Auth: HTTP Basic (user/password зберігаються в ir.config_parameter)

Налаштування в Odoo (одноразово через shell):
  env['ir.config_parameter'].set_param('pipedrive.webhook.user', 'pipedrive')
  env['ir.config_parameter'].set_param('pipedrive.webhook.password', 'СЕКРЕТНИЙ_ТОКЕН')
  # Custom field keys (після отримання через Pipedrive API):
  env['ir.config_parameter'].set_param('pipedrive.field.label', 'HASH_KEY')
  env['ir.config_parameter'].set_param('pipedrive.field.financing_type', 'HASH_KEY')
  env['ir.config_parameter'].set_param('pipedrive.field.credit_specialist', 'HASH_KEY')
"""
import base64
import logging
import re

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# --- Маппінги (дублюються з import-скриптів) ---

OWNER_MAP = {
    'наталія гадайчук':          'гадайчук',
    'юрій ходаківський':         'ходаківський',
    'андрій селезньов':          'селезньов',
    'станіслав бобровицький':    'бобровицький',
    'ігор бєлік':                None,
    'сергій толочко':            'толочко',
    'максим сидоров':            'сидоров',
    'богдан безверхий':          None,
    'олександр достовалов':      'достовалов',
    'віталій стоцький':          'стоцький',
    'микола тубіш':              'тубіш',
    'юрій лисенко':              'лисенко',
    'яна курнаєва':              'курнаєва',
    'леся':                      'радіоненко',
    'павлов дмитро':             'павлов',
    'олександр коростіль':       'коростіль',
    'ксенія коваленко':          'сущенко',
    'оксана коваленко':          'сущенко',
    'дмитро петров':             'петров',
    'ірина бакуменко':           'бакуменко',
    'ольга вергун':              None,
    'ольга':                     None,
    'олександр пилипенко':       None,
}

FINANCING_MAP = {
    'Власні':                   'own',
    'Кредитні':                 'credit',
    'Власні (аванс)/Кредитні':  'mixed',
}

PROJECT_TYPE_MAP = {
    'СЕС':       'ses',
    'УЗЕ':       'uze',
    'СЕС + УЗЕ': 'ses_uze',
    'УЗЕ, СЕС':  'ses_uze',
    'СЕС+УЗЕ':   'ses_uze',
}

CREDIT_SPECIALIST_MAP = {
    'Оксана Коваленко':    'сущенко',
    'Яна Курнаєва':        'курнаєва',
    'Леся Радіоненко':     'радіоненко',
    'Олександр Коростіль': 'коростіль',
}

# Pipedrive option IDs для custom fields (отримані через API /dealFields)
# label (set) → project_type
LABEL_OPTION_MAP = {
    137: 'uze',
    138: 'ses',
    139: 'ses_uze',
}

# financing_type (enum) → financing_type
FINANCING_OPTION_MAP = {
    227: 'own',
    228: 'credit',
    229: 'mixed',
}

# credit_specialist (enum) → surname для пошуку в res.users
CREDIT_SPECIALIST_OPTION_MAP = {
    230: 'сущенко',    # Оксана Коваленко
    231: 'коростіль',
    232: 'радіоненко',
    233: 'курнаєва',
    265: None,         # Владислав Карась — не в Odoo
}

# Pipedrive activity key_string → (Odoo type name, display label, icon)
# key_strings отримано через GET /activityTypes
ACTIVITY_KEY_MAP = {
    'call':                       ('Телефонний дзвінок Клієнту', 'Телефонний дзвінок Клієнту', '📞'),
    'nedozvon':                   ('Недозвон',                   'Недозвон',                   '📵'),
    'telefonniy_dzvnok_partners': ('Телефонний дзвінок Клієнту', 'Тел. дзвінок (партнерство)', '📞'),
    'vdpravka_kp_uzeses':         ('Надіслати КП',               'Надіслано лист/КП',          '✉️'),
    'peredacha_kartki_na_mp__pk1':('Передача ліда',              'Передача картки (новий лід)','🚀'),
    'peredacha_kartki_na_mp__pk2':('Передача ліда',              'Передача картки (старий лід)','🚀'),
    'peredacha_kartki_na_mp__pk': ('Передача ліда',              'Передача картки',            '🚀'),
    'peredacha_kartki_na_mvk':    ('Передача ліда',              'Передача картки на МВК',     '🚀'),
    'poshuk_lpr':                 ('Обробка нових лідів',        'Обробка нових',              '🔄'),
    'vdpravka_pkp':               ('Відправка ПКП',              'Відправка ПКП',              '✉️'),
    'email':                      ('Надіслати КП',               'Ел. пошта',                  '✉️'),
    'meeting':                    ('Онлайн-зустріч',             'Онлайн-зустріч',             '🖥️'),
    'oflayn_zustrch':             ('Офлайн-зустріч',             'Офлайн-зустріч',             '🤝'),
    'task':                       ('Завдання КЦ',                'Завдання',                   '✅'),
    'zavdannya_realzatsya_proek': ('Завдання КЦ',                'Завдання (реалізація)',       '✅'),
    'deadline':                   ('Завдання КЦ',                'Термін виконання',            '✅'),
    'task1':                      ('Завдання КЦ',                'Завдання',                   '✅'),
    'inbound_call':               ('Вхідний дзвінок',            'Вхідний дзвінок',            '📲'),
    'vkhdniy_dzvnok':             ('Вхідний дзвінок',            'Вхідний дзвінок',            '📲'),
    'missed_call':                ('Недозвон',                   'Пропущений дзвінок',         '📵'),
    'propushcheniy_dzvnok':       ('Недозвон',                   'Пропущений дзвінок',         '📵'),
    'outbound_call':              ('Вихідний дзвінок',           'Вихідний дзвінок',           '📞'),
    'vikhdniy_dzvnok':            ('Вихідний дзвінок',           'Вихідний дзвінок',           '📞'),
    'lunch':                      (None,                         'Діловий обід',               '🍽️'),
    'nshe':                       (None,                         'Дублі та інше',              '📌'),
    'nevdpovdniy_ld_povernennya': (None,                         'Невідповідний лід',          '❌'),
    'priynyato_v_robotu':         (None,                         'Прийнято в роботу',          '✅'),
    'povernennya_kartki_na_oper': (None,                         'Повернення на оператора',    '⏸️'),
    'vdguk_vd_klyenta_fdbek':     (None,                         'Відгук від клієнта',         '💬'),
    'provedennya_navchannya_ban': (None,                         'Проведення навчання',        '📚'),
    'pdgotovka_dogovoru':         (None,                         'Підготовка договору',        '📝'),
}

# Fallback: display name → Odoo type (для зворотної сумісності з v1 і subject-lookup)
ACTIVITY_NAME_MAP = {
    'Телефонний дзвінок Клієнту':                                  'Телефонний дзвінок Клієнту',
    'Вихідний дзвінок':                                            'Вихідний дзвінок',
    'Вхідний дзвінок':                                             'Вхідний дзвінок',
    'Недозвон':                                                    'Недозвон',
    'Пропущений дзвінок':                                          'Недозвон',
    'Завдання':                                                    'Завдання КЦ',
    'Завдання (реалізація проекту / взаємодія з технічним Департаментом)': 'Завдання КЦ',
    'Обробка нових':                                               'Обробка нових лідів',
    'Надіслано лист/ КП':                                          'Надіслати КП',
    'Відправка ПКП':                                               'Відправка ПКП',
    'Онлайн-зустріч':                                              'Онлайн-зустріч',
    'Офлайн-зустріч з Клієнтом / Партнером':                       'Офлайн-зустріч',
    'Передача картки на МП / ПКП новий лід':                       'Передача ліда',
    'Передача картки на МП / ПКП старий лід':                      'Передача ліда',
    'Передача картки на МВК':                                      'Передача ліда',
}


def _normalize_phone(p):
    d = re.sub(r'[^0-9]', '', str(p).strip())
    if len(d) == 10 and d.startswith('0'):
        d = '380' + d[1:]
    if d.startswith('380') and len(d) == 12:
        return d
    return None


class PipedriveWebhook(http.Controller):

    # ------------------------------------------------------------------ #
    #  Основний endpoint                                                   #
    # ------------------------------------------------------------------ #

    @http.route(
        '/pipedrive/webhook',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def handle(self, **kw):
        """Приймає webhook від Pipedrive, диспетчеризує по типу події."""
        if not self._check_auth():
            _logger.warning('Pipedrive webhook: невірна авторизація')
            return {'status': 'unauthorized'}

        data = request.get_json_data()
        if not data:
            return {'status': 'empty'}

        meta = data.get('meta', {})

        # Pipedrive v2: meta.entity + data['data'] + action: change/create/delete
        # Pipedrive v1: meta.object + data['current'] + action: updated/added/deleted
        obj    = meta.get('entity') or meta.get('object')
        action = meta.get('action', '')

        # Нормалізуємо action до v1-стилю для уніфікованої логіки
        action_norm = {'change': 'updated', 'create': 'added', 'delete': 'deleted'}.get(action, action)

        # v2: поточні дані в data['data'], v1: в data['current']
        current  = data.get('data') or data.get('current') or {}
        previous = data.get('previous') or {}

        _logger.info('Pipedrive webhook: %s.%s (raw=%s) id=%s',
                     obj, action_norm, action, meta.get('entity_id') or meta.get('id'))

        try:
            env = request.env(user=request.env.ref('base.user_admin').id)

            if obj == 'deal':
                self._on_deal(env, action_norm, current, previous)
            elif obj == 'activity':
                self._on_activity(env, action_norm, current)
            elif obj == 'person':
                self._on_person(env, action_norm, current)
            elif obj == 'organization':
                self._on_organization(env, action_norm, current)

        except Exception as e:
            _logger.error('Pipedrive webhook error (%s.%s): %s', obj, action, e, exc_info=True)

        return {'status': 'ok'}

    # ------------------------------------------------------------------ #
    #  Auth                                                                #
    # ------------------------------------------------------------------ #

    def _check_auth(self):
        auth_header = request.httprequest.headers.get('Authorization', '')
        if not auth_header.startswith('Basic '):
            return False
        try:
            decoded = base64.b64decode(auth_header[6:]).decode('utf-8')
            user, password = decoded.split(':', 1)
        except Exception:
            return False

        cfg = request.env['ir.config_parameter'].sudo()
        expected_user = cfg.get_param('pipedrive.webhook.user', '')
        expected_pass = cfg.get_param('pipedrive.webhook.password', '')
        return user == expected_user and password == expected_pass

    # ------------------------------------------------------------------ #
    #  Deal                                                                #
    # ------------------------------------------------------------------ #

    def _on_deal(self, env, action, current, previous):
        pd_id = current.get('id')
        if not pd_id:
            return

        lead = env['crm.lead'].search([('pipedrive_deal_id', '=', pd_id)], limit=1)

        if not lead and action == 'deleted':
            return

        vals = self._build_deal_vals(env, current)

        if not lead:
            if action not in ('added', 'updated'):
                return
            vals['pipedrive_deal_id'] = pd_id
            vals['type'] = 'opportunity'
            lead = env['crm.lead'].create(vals)
            _logger.info('Pipedrive: створено нагоду id=%s "%s"', lead.id, lead.name)
        else:
            # Не перезаписуємо поля якщо вони вже заповнені в Odoo і не змінились в Pipedrive
            if not vals:
                return
            lead.write(vals)
            _logger.info('Pipedrive: оновлено нагоду id=%s', lead.id)

        # Статус won/lost
        status = current.get('status')
        if status == 'won' and not lead.stage_id.is_won:
            lead.action_set_won()
        elif status == 'lost' and lead.active:
            lead.write({'active': False, 'probability': 0})
        elif status == 'open' and not lead.active:
            lead.write({'active': True})

    def _build_deal_vals(self, env, current):
        vals = {}

        title = current.get('title')
        if title:
            vals['name'] = title

        # Команда і стейдж
        pipeline = (current.get('pipeline_id') or {})
        pipeline_name = pipeline.get('name', '') if isinstance(pipeline, dict) else ''
        team = self._get_team(env, pipeline_name)
        if team:
            vals['team_id'] = team.id

        stage_data = current.get('stage_id')
        if isinstance(stage_data, dict):
            stage_name = stage_data.get('name', '')
        elif isinstance(stage_data, int):
            stage_name = ''
        else:
            stage_name = str(stage_data) if stage_data else ''
        if stage_name:
            stage = self._get_or_find_stage(env, stage_name)
            if stage:
                vals['stage_id'] = stage.id

        # Власник
        owner = current.get('user_id')
        if isinstance(owner, dict):
            owner_name = owner.get('name', '')
            uid = self._find_user(env, owner_name)
            if uid:
                vals['user_id'] = uid

        # Компанія
        org = current.get('org_id')
        if isinstance(org, dict):
            org_pd_id = org.get('value')
        else:
            org_pd_id = org
        if org_pd_id:
            partner = self._find_org(env, org_pd_id)
            if partner:
                vals['partner_id'] = partner.id

        # Контакт
        person = current.get('person_id')
        if isinstance(person, dict):
            person_pd_id = person.get('value')
        else:
            person_pd_id = person
        if person_pd_id:
            contact = env['res.partner'].search(
                [('pipedrive_person_id', '=', person_pd_id)], limit=1
            )
            if contact:
                vals['contact_id'] = contact.id  # Odoo standard field

        # Custom fields (ключі з ir.config_parameter)
        cfg = env['ir.config_parameter'].sudo()

        # label (set) → project_type; Pipedrive надсилає список option ID [138] або текст
        label_key = cfg.get_param('pipedrive.field.label', 'label')
        if label_key in current:
            label_val = current[label_key]
            ptype = False
            if isinstance(label_val, list):
                first = label_val[0] if label_val else None
                if isinstance(first, int):
                    ptype = LABEL_OPTION_MAP.get(first)
                elif first:
                    ptype = PROJECT_TYPE_MAP.get(str(first))
            elif isinstance(label_val, int):
                ptype = LABEL_OPTION_MAP.get(label_val)
            elif label_val:
                ptype = PROJECT_TYPE_MAP.get(str(label_val))
            if ptype:
                vals['project_type'] = ptype

        # financing_type (enum) → Pipedrive надсилає int option ID або текст
        financing_key = cfg.get_param('pipedrive.field.financing_type', '')
        if financing_key and financing_key in current:
            fin_val = current[financing_key]
            if isinstance(fin_val, int):
                ftype = FINANCING_OPTION_MAP.get(fin_val)
            else:
                ftype = FINANCING_MAP.get(str(fin_val), False)
            if ftype:
                vals['financing_type'] = ftype

        # credit_specialist (enum) → int option ID або текст
        credit_key = cfg.get_param('pipedrive.field.credit_specialist', '')
        if credit_key and credit_key in current:
            cs_val = current.get(credit_key)
            if isinstance(cs_val, int):
                surname = CREDIT_SPECIALIST_OPTION_MAP.get(cs_val)
                if surname:
                    user = env['res.users'].search([('name', 'ilike', surname)], limit=1)
                    if user:
                        vals['credit_specialist_id'] = user.id
            elif cs_val:
                uid = self._find_credit_specialist(env, str(cs_val))
                if uid:
                    vals['credit_specialist_id'] = uid

        # project_number (text) → № проекту
        project_num_key = cfg.get_param('pipedrive.field.project_number', '')
        if project_num_key and project_num_key in current:
            pnum = current.get(project_num_key)
            if pnum:
                vals['project_number'] = str(pnum)

        return vals

    # ------------------------------------------------------------------ #
    #  Activity                                                            #
    # ------------------------------------------------------------------ #

    def _on_activity(self, env, action, current):
        # Обробляємо лише завершені активності
        if not current.get('done'):
            return

        pd_act_id = current.get('id')
        if not pd_act_id:
            return

        # Перевіряємо чи вже імпортовано
        ext_name = 'pipedrive_act_%d' % pd_act_id
        existing = env['ir.model.data'].sudo().search([
            ('module', '=', '__import__'),
            ('model', '=', 'mail.message'),
            ('name', '=', ext_name),
        ], limit=1)
        if existing:
            return  # вже є

        # Знаходимо прив'язку
        res_model = False
        res_id = False

        deal_id = current.get('deal_id')
        if deal_id:
            lead = env['crm.lead'].search([('pipedrive_deal_id', '=', deal_id)], limit=1)
            if lead:
                res_model = 'crm.lead'
                res_id = lead.id

        if not res_id:
            person_id = current.get('person_id')
            if person_id:
                partner = env['res.partner'].search(
                    [('pipedrive_person_id', '=', person_id)], limit=1
                )
                if partner:
                    res_model = 'res.partner'
                    res_id = partner.id

        if not res_id:
            _logger.debug('Pipedrive activity %s: no target found', pd_act_id)
            return

        # Автор
        assigned = current.get('user_id', {})
        assigned_name = assigned.get('name', '') if isinstance(assigned, dict) else ''
        author_pid = self._get_author_pid(env, assigned_name)

        # Тип активності — шукаємо спочатку по key_string (v2), потім по display name (v1/subject)
        type_key = str(current.get('type') or '')
        note    = str(current.get('note') or '').strip()
        subject = str(current.get('subject') or '').strip()

        key_entry = ACTIVITY_KEY_MAP.get(type_key)
        if key_entry:
            odoo_type_name, display_label, icon = key_entry
        else:
            # fallback: шукаємо по subject або display name
            odoo_type_name = ACTIVITY_NAME_MAP.get(subject) or ACTIVITY_NAME_MAP.get(type_key)
            display_label  = subject or type_key
            icon           = '📌'

        done_mark = '✓'

        # Контактна особа
        person_data = current.get('person_id')
        if isinstance(person_data, dict):
            contact_name = person_data.get('name', '')
        else:
            contact_name = ''

        lines = ['<strong>%s %s</strong> %s' % (icon, display_label, done_mark)]
        # subject показуємо лише якщо він відрізняється від display_label
        if subject and subject != display_label:
            lines.append('<em>%s</em>' % subject)
        if contact_name:
            lines.append('Контакт: %s' % contact_name)
        if assigned_name:
            lines.append('Виконавець: %s' % assigned_name)
        if note:
            lines.append('<br>%s' % note)
        body = '<p>' + '<br>'.join(lines) + '</p>'

        # mail_activity_type_id
        activity_type = False
        if odoo_type_name:
            activity_type = env['mail.activity.type'].search(
                [('name', 'ilike', odoo_type_name)], limit=1
            )

        mt_activities = env.ref('mail.mt_activities').id

        # Дата
        done_date = current.get('marked_as_done_time') or current.get('due_date')
        if done_date:
            date_str = str(done_date)[:19].replace('T', ' ')
        else:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        msg = env['mail.message'].sudo().create({
            'res_id':                res_id,
            'model':                 res_model,
            'body':                  body,
            'date':                  date_str,
            'author_id':             author_pid,
            'message_type':          'comment',
            'subtype_id':            mt_activities,
            'mail_activity_type_id': activity_type.id if activity_type else False,
        })

        env['ir.model.data'].sudo().create({
            'module': '__import__',
            'model':  'mail.message',
            'name':   ext_name,
            'res_id': msg.id,
        })

        _logger.info('Pipedrive activity %s → message %s (%s)', pd_act_id, msg.id, res_model)

    # ------------------------------------------------------------------ #
    #  Person                                                              #
    # ------------------------------------------------------------------ #

    def _on_person(self, env, action, current):
        pd_person_id = current.get('id')
        if not pd_person_id:
            return

        partner = env['res.partner'].search(
            [('pipedrive_person_id', '=', pd_person_id)], limit=1
        )
        if not partner:
            return

        # Оновлюємо email
        emails = current.get('email') or []
        if isinstance(emails, list) and emails:
            first_email = next(
                (e.get('value') for e in emails if e.get('value') and '@' in e.get('value', '')),
                None
            )
            if first_email and first_email != partner.email:
                partner.write({'email': first_email})

        # Додаємо нові телефони (не видаляємо існуючі)
        phones = current.get('phone') or []
        if isinstance(phones, list):
            existing_phones = set(partner.phone_ids.mapped('phone'))
            has_primary = bool(existing_phones)
            new_added = 0
            for ph_obj in phones:
                raw = ph_obj.get('value', '') if isinstance(ph_obj, dict) else str(ph_obj)
                norm = _normalize_phone(raw)
                if norm and norm not in existing_phones:
                    env['res.partner.phone'].create({
                        'partner_id': partner.id,
                        'phone':      norm,
                        'phone_type': 'work',
                        'is_primary': not has_primary and new_added == 0,
                        'sequence':   10 + new_added,
                    })
                    existing_phones.add(norm)
                    new_added += 1

        if action == 'updated':
            name = current.get('name')
            if name and name != partner.name:
                partner.write({'name': name})

    # ------------------------------------------------------------------ #
    #  Organization                                                        #
    # ------------------------------------------------------------------ #

    def _on_organization(self, env, action, current):
        pd_org_id = current.get('id')
        if not pd_org_id:
            return

        imd = env['ir.model.data'].sudo().search([
            ('module', '=', '__import__'),
            ('model', '=', 'res.partner'),
            ('name', '=', 'pipedrive_org_%d' % pd_org_id),
        ], limit=1)
        if not imd:
            return

        partner = env['res.partner'].browse(imd.res_id)
        if not partner.exists():
            return

        name = current.get('name')
        if name and name != partner.name:
            partner.write({'name': name})
            _logger.info('Pipedrive org %s: оновлено назву → %s', pd_org_id, name)

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _get_team(self, env, pipeline_name):
        if not pipeline_name:
            return env['crm.team'].search([('name', 'ilike', 'Оператор')], limit=1)
        p = str(pipeline_name)
        if 'Менеджер' in p or 'Sales' in p:
            return env['crm.team'].search([('name', 'ilike', 'Sales')], limit=1)
        if 'кредит' in p.lower():
            return env['crm.team'].search([('name', 'ilike', 'кредит')], limit=1)
        return env['crm.team'].search([('name', 'ilike', 'Оператор')], limit=1)

    def _get_or_find_stage(self, env, stage_name):
        if not stage_name:
            return False
        stage = env['crm.stage'].search([('name', 'ilike', stage_name)], limit=1)
        return stage or False

    def _find_user(self, env, name_str):
        if not name_str:
            return False
        key = str(name_str).split('/')[0].strip().lower()
        surname = OWNER_MAP.get(key)
        if surname is False:
            return False  # явний None в маппінгу → Admin не призначаємо
        if surname:
            user = env['res.users'].search([('name', 'ilike', surname)], limit=1)
            return user.id if user else False
        return False

    def _find_credit_specialist(self, env, name_str):
        if not name_str:
            return False
        for key, surname in CREDIT_SPECIALIST_MAP.items():
            if key.lower() in name_str.lower():
                user = env['res.users'].search([('name', 'ilike', surname)], limit=1)
                return user.id if user else False
        return False

    def _find_org(self, env, pd_org_id):
        imd = env['ir.model.data'].sudo().search([
            ('module', '=', '__import__'),
            ('model', '=', 'res.partner'),
            ('name', '=', 'pipedrive_org_%d' % int(pd_org_id)),
        ], limit=1)
        if imd:
            return env['res.partner'].browse(imd.res_id)
        return False

    def _get_author_pid(self, env, username):
        if not username:
            return env.ref('base.user_admin').partner_id.id
        key = str(username).split('/')[0].strip().lower()
        surname = OWNER_MAP.get(key)
        if surname:
            user = env['res.users'].search([('name', 'ilike', surname)], limit=1)
            if user:
                return user.partner_id.id
        return env.ref('base.user_admin').partner_id.id
