"""Inspect loaded configuration without querying users, the database or AI."""
from django.core.management.base import BaseCommand

from hwyd.ai_service import (SummaryServiceError, configuration, message_limit,
                             request_body, request_metrics, settings_diagnostics)
from hwyd.habit_summary import compact_json


class Command(BaseCommand):
    help = 'Show safe AI configuration and a synthetic request budget; never contacts the AI service.'

    def handle(self, *args, **options):
        result = {**settings_diagnostics(), 'scope': 'this_management_process', 'network_used': False}
        try:
            _, _, _, tokens = configuration()
            message_limit()
            # Synthetic values only: no database reads or personal data.
            facts = dict(month='2026-01', start='2026-01-01', end='2026-01-31', through='2026-01-31',
                         habit_count=1, completed=1, available=1, percent=100)
            body = request_body(facts, [{'name': 'Habit', 'completed': 1, 'available': 1}], tokens)
            result.update(configuration_valid=True, synthetic_request_fits=True, **request_metrics(body))
        except SummaryServiceError as error:
            result.update(configuration_valid=error.code != 'unavailable', synthetic_request_fits=False,
                          code=error.code, **error.diagnostics)
        self.stdout.write(compact_json(result))
