import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class RaytonRingostatExcludedPhone(models.Model):
    _name = 'rayton.ringostat.excluded.phone'
    _description = 'Виключені телефони (внутрішні номери співробітників)'
    _order = 'employee_name, phone'
    _rec_name = 'employee_name'

    phone = fields.Char('Номер телефону', required=True, index=True)
    employee_name = fields.Char('ПІБ / Примітка')

    @api.model
    def _get_excluded_set(self):
        """Return a set of last-9-digit suffixes of all excluded phones.

        Calls where the external party's phone matches any suffix in this set
        are considered internal (employee-to-employee) and should be skipped.
        """
        self.env.cr.execute(
            "SELECT phone FROM rayton_ringostat_excluded_phone WHERE phone IS NOT NULL"
        )
        result = set()
        for (ph,) in self.env.cr.fetchall():
            digits = ''.join(c for c in ph if c.isdigit())
            if len(digits) >= 7:
                result.add(digits[-9:])
        return result

    @api.model
    def is_internal(self, phone_number):
        """Return True if the given phone number belongs to an internal employee."""
        if not phone_number:
            return False
        digits = ''.join(c for c in phone_number if c.isdigit())
        if len(digits) < 7:
            return False
        return digits[-9:] in self._get_excluded_set()
