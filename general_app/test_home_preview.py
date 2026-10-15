"""The public example uses synthetic data and the tracker's five-day window."""
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .test_public_pages import PageElements
from .views import HomeView


class HomePreviewTests(TestCase):
    def test_phone_window_has_five_consecutive_days_including_today_at_month_edges(self):
        cases = [(date(2026, 10, day), start) for day, start in
                 ((1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (15, 12), (30, 27), (31, 27))]
        cases += [(date(2027, 2, 28), 24), (date(2028, 2, 29), 25), (date(2026, 4, 30), 26)]
        for today, start in cases:
            with self.subTest(today=today), patch('general_app.views.timezone.localdate', return_value=today):
                with self.assertNumQueries(0):
                    context = HomeView().get_context_data()
                visible = [day['number'] for day in context['preview_days'] if day['mobile_visible']]
                self.assertEqual(visible, list(range(start, start + 5)))
                self.assertIn(today.day, visible)
                for habit in context['preview_habits']:
                    self.assertEqual([cell['number'] for cell in habit['cells'] if cell['mobile_visible']], visible)
                self.assertEqual([cell['number'] for cell in context['preview_group']['cells'] if cell['mobile_visible']], visible)

    def test_example_has_accessible_local_controls_and_real_sound_assets(self):
        with patch('general_app.views.timezone.localdate', return_value=date(2026, 10, 15)):
            response = self.client.get('/')
        elements = PageElements(response)
        groups = [button for button in elements.tags('button') if 'aria-expanded' in button]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['aria-expanded'], 'true')
        self.assertEqual(groups[0]['aria-controls'].split(), ['preview-habit-1', 'preview-habit-2', 'preview-habit-3'])
        cells = [button for button in elements.tags('button') if 'data-preview-cell' in button]
        self.assertEqual(len(cells), 3 * 31)
        self.assertTrue(all(button['type'] == 'button' and 'aria-pressed' in button and 'disabled' in button for button in cells))
        self.assertEqual(len([el for _, el in elements.elements if el.get('role') == 'progressbar']), 31)
        self.assertContains(response, 'data-sound-on="/static/hwyd/audio/on.MP3"')
        self.assertContains(response, 'data-sound-off="/static/hwyd/audio/off.MP3"')
        self.assertContains(response, 'Изменения в примере не сохраняются.')
        self.assertNotContains(response, 'data-open-group-url')
        self.assertNotContains(response, 'data-activity-id')

    def test_home_settings_link_targets_modal_and_survives_login_next(self):
        destination = reverse('index') + '#settings'
        guest = PageElements(self.client.get('/'))
        entry_links = [a['href'] for a in guest.tags('a') if a.get('href', '').startswith(reverse('entry'))]
        self.assertTrue(any(parse_qs(urlsplit(link).query).get('next') == [destination] for link in entry_links))
        self.client.force_login(get_user_model().objects.create_user('preview-modal-link'))
        page = self.client.get('/')
        self.assertContains(page, f'href="{destination}"')
        self.assertNotContains(page, reverse('edit_settings'))
