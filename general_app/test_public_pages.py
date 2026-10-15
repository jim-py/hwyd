"""Public routing, metadata, accounts and the isolated presentation layer."""
from html.parser import HTMLParser
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, TestCase, override_settings
from django.urls import resolve, reverse

from .views import HomeView


class PageElements(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.elements = []
        self.feed(response.content.decode())

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def tags(self, name):
        return [attrs for tag, attrs in self.elements if tag == name]


class PublicPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('public-page-user', password='Only-Local-Habits-47!')

    def test_root_is_public_home_for_guest_and_authenticated_visitors(self):
        self.assertEqual(reverse('home'), '/')
        for signed_in in (False, True):
            if signed_in:
                self.client.force_login(self.user)
            with self.subTest(signed_in=signed_in):
                response = self.client.get(reverse('home'))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'general_app/home.html')
                self.assertContains(response, 'трекер привычек')
                self.assertContains(response, 'Настройки → Обучение')
                for removed in ('Tempus', 'Mentis', 'трекер времени', 'База знаний', 'бюджетом', 'экосистем'):
                    self.assertNotContains(response, removed)
                self.assertEqual(len(PageElements(response).tags('h1')), 1)
                if signed_in:
                    self.assertContains(response, 'Открыть мой трекер')
                else:
                    links = PageElements(response).tags('a')
                    starts = [parse_qs(urlsplit(link.get('href', '')).query) for link in links]
                    self.assertIn({'type': ['register'], 'next': [reverse('index')]}, starts)

    def test_home_defaults_to_habitus_and_keeps_week_example_as_a_native_choice(self):
        response = self.client.get('/')
        elements = PageElements(response)
        choices = [tag for tag in elements.tags('input') if tag.get('name') == 'public-preview-view']
        self.assertEqual([choice['value'] for choice in choices], ['habitus', 'week'])
        self.assertTrue(all(choice['type'] == 'radio' for choice in choices))
        self.assertIn('checked', choices[0])
        self.assertNotIn('checked', choices[1])
        labels = {tag['for'] for tag in elements.tags('label')}
        ids = [tag.get('id') for _, tag in elements.elements if 'id' in tag]
        for choice in choices:
            self.assertIn(choice['id'], labels)
            self.assertEqual(ids.count(choice['aria-controls']), 1)
        self.assertTemplateUsed(response, 'general_app/includes/home_habitus_preview.html')
        self.assertEqual(len(elements.tags('table')), 2)
        self.assertContains(response, 'class="public-habit-table"')
        self.assertContains(response, '<caption>Иллюстрация с условными привычками и отметками.</caption>', html=True)
        self.assertNotContains(response, 'id="myTable"')
        self.assertNotContains(response, 'data-activity-id=')
        for path in (reverse('about'), reverse('entry'), '/missing-preview-page/'):
            other = self.client.get(path)
            self.assertNotContains(other, 'public-preview-view', status_code=other.status_code)

    def test_habitus_example_uses_current_calendar_and_synthetic_marks_without_queries(self):
        for today, total in ((date(2028, 2, 29), 29), (date(2027, 2, 28), 28), (date(2026, 10, 15), 31)):
            with self.subTest(today=today), patch('general_app.views.timezone.localdate', return_value=today):
                with self.assertNumQueries(0):
                    context = HomeView().get_context_data()
                days = context['preview_days']
                self.assertEqual(context['preview_month'], today.replace(day=1))
                self.assertEqual([day['number'] for day in days], list(range(1, total + 1)))
                self.assertEqual([day['number'] for day in days if day['today']], [today.day])
                self.assertEqual([day['weekend'] for day in days],
                                 [today.replace(day=n).weekday() >= 5 for n in range(1, total + 1)])
                self.assertEqual([habit['name'] for habit in context['preview_habits']], ['Читать', 'Гулять', 'Зарядка'])
                self.assertEqual(context['preview_group']['name'], 'Здоровье')
                for index, cell in enumerate(context['preview_group']['cells']):
                    done = sum(habit['cells'][index]['done'] for habit in context['preview_habits'])
                    self.assertEqual(cell['percent'], round(done / 3 * 100))
                for habit in context['preview_habits']:
                    self.assertEqual(len(habit['cells']), total)
                    self.assertTrue(any(cell['done'] for cell in habit['cells']))
                    self.assertTrue(all(not cell['done'] for cell in habit['cells'] if cell['number'] >= today.day))

    def test_both_old_home_variants_redirect_directly_and_preserve_query(self):
        query = 'utm_source=guide&next=%2Fhabitus%2F&tag=a&tag=b'
        for signed_in in (False, True):
            if signed_in:
                self.client.force_login(self.user)
            for path in ('/home', '/home/'):
                with self.subTest(signed_in=signed_in, path=path):
                    response = self.client.get(path + '?' + query, follow=True)
                    self.assertEqual(response.redirect_chain, [('/?' + query, 301)])
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.client.head(path).status_code, 301)

    def test_nested_account_and_guide_routes_keep_their_addresses(self):
        for name, path in (('entry', '/home/entry/'), ('about', '/home/about/'),
                           ('profile', '/home/profile/'), ('logout', '/home/logout/')):
            self.assertEqual(reverse(name), path)
            self.assertEqual(resolve(path).url_name, name)
        self.assertEqual(resolve('/home/guides/main_toolbar/viewed/').func.__name__, 'mark_guide_viewed')
        self.assertEqual(reverse('guide_opened', args=['main_toolbar']), '/home/guides/main_toolbar/opened/')

    @override_settings(PUBLIC_SITE_ORIGIN='https://public.example.test/')
    def test_metadata_has_one_query_free_absolute_canonical_and_matching_og_url(self):
        response = self.client.get('/?utm_source=example&next=/other/', HTTP_HOST='localhost')
        elements = PageElements(response)
        canonicals = [tag['href'] for tag in elements.tags('link') if tag.get('rel') == 'canonical']
        self.assertEqual(canonicals, ['https://public.example.test/'])
        properties = {tag.get('property'): tag.get('content') for tag in elements.tags('meta')}
        self.assertEqual(properties['og:url'], canonicals[0])
        self.assertEqual(properties['og:type'], 'website')
        self.assertEqual(properties['og:locale'], 'ru_RU')
        self.assertIn('Habitus', properties['og:title'])
        descriptions = [tag['content'] for tag in elements.tags('meta') if tag.get('name') == 'description']
        self.assertEqual(len(descriptions), 1)
        self.assertIn('привычек', descriptions[0])
        self.assertContains(response, 'Трекер привычек онлайн — Habitus | Productivum')
        self.assertNotContains(response, 'noindex')
        self.assertNotContains(response, 'name="keywords"')

    def test_default_canonical_uses_confirmed_public_origin(self):
        response = self.client.get('/', HTTP_HOST='localhost')
        self.assertContains(response, '<link rel="canonical" href="https://productivum.ru/">', html=True)

    def test_invalid_origin_configuration_is_not_published_as_a_canonical(self):
        for origin in ('localhost', 'https://public.example.test/path', 'https://public.example.test?q=x',
                       'https://user:password@public.example.test', 'javascript:alert(1)'):
            with self.subTest(origin=origin), override_settings(PUBLIC_SITE_ORIGIN=origin):
                with self.assertRaises(ImproperlyConfigured):
                    self.client.get('/')

    def test_five_pages_share_one_scoped_theme_and_semantic_content_without_js(self):
        for path in ('/', reverse('about'), reverse('entry') + '?type=login',
                     reverse('entry') + '?type=register', '/missing-public-page/'):
            with self.subTest(path=path):
                response = self.client.get(path)
                status = 404 if path == '/missing-public-page/' else 200
                self.assertEqual(response.status_code, status)
                elements = PageElements(response)
                self.assertEqual(len(elements.tags('h1')), 1)
                self.assertEqual(len(elements.tags('main')), 1)
                self.assertEqual(len(elements.tags('nav')), 1)
                buttons = [button for button in elements.tags('button') if 'data-public-theme-control' in button]
                self.assertEqual(len(buttons), 1)
                self.assertEqual(buttons[0]['type'], 'button')
                self.assertEqual(len([li for li in elements.tags('li') if 'data-public-theme-item' in li and 'hidden' in li]), 1)
                scripts = [script['src'] for script in elements.tags('script') if script.get('src')]
                expected = ['/static/general_app/js/public-theme.js?v=20261015']
                if path == '/':
                    expected.append('/static/general_app/js/home-preview.js?v=20261015-interactive')
                self.assertEqual(scripts, expected)
                self.assertContains(response, 'data-public-theme="auto"', status_code=status)
                self.assertContains(response, 'productivum.publicTheme', status_code=status)
                html = response.content.decode()
                self.assertLess(html.index("localStorage.getItem"), html.index('general_app/css/public.css'))
                self.assertNotContains(response, 'admin/theme.js', status_code=status)
                self.assertNotContains(response, 'theme-schedule.js', status_code=status)
                for image in elements.tags('img'):
                    self.assertIn('alt', image)
                    self.assertIn('width', image)
                    self.assertIn('height', image)

    def test_only_selected_entry_form_is_rendered_with_labels_and_autofill(self):
        for mode, fields in (('login', {'username': 'username', 'password': 'current-password'}),
                             ('register', {'first_name': 'given-name', 'last_name': 'family-name',
                                           'email': 'email', 'username': 'username',
                                           'password1': 'new-password', 'password2': 'new-password'})):
            response = self.client.get(reverse('entry'), {'type': mode, 'next': '/habitus/?a=1&b=2'})
            elements = PageElements(response)
            self.assertEqual(len(elements.tags('form')), 1)
            labels = {label['for'] for label in elements.tags('label')}
            inputs = {field['name']: field for field in elements.tags('input')}
            for name, autocomplete in fields.items():
                self.assertEqual(inputs[name]['autocomplete'], autocomplete)
                self.assertIn(inputs[name]['id'], labels)
            self.assertIn('csrfmiddlewaretoken', inputs)
            action = elements.tags('form')[0]['action']
            self.assertEqual(parse_qs(urlsplit(action).query), {'type': [mode], 'next': ['/habitus/?a=1&b=2']})
            submit = elements.tags('button')[-1]
            self.assertEqual(submit['name'], mode)

    def test_invalid_login_keeps_next_username_and_accessible_errors(self):
        destination = '/habitus/?source=home&step=1'
        url = reverse('entry') + '?' + urlencode({'type': 'login', 'next': destination})
        response = self.client.post(url, {'login': '', 'username': 'missing-user', 'password': 'invalid'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['next'], destination)
        elements = PageElements(response)
        inputs = {field['name']: field for field in elements.tags('input')}
        self.assertEqual(inputs['username']['value'], 'missing-user')
        self.assertEqual(inputs['username']['aria-describedby'], 'alerts-container')
        self.assertNotIn('value', inputs['password'])
        self.assertEqual(parse_qs(urlsplit(elements.tags('form')[0]['action']).query)['next'], [destination])
        self.assertContains(response, 'role="alert"')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_invalid_registration_keeps_fields_and_next_without_creating_a_user(self):
        before = get_user_model().objects.count()
        destination = '/habitus/?source=registration&step=1'
        response = self.client.post(reverse('entry') + '?' + urlencode({'next': destination}), {
            'register': '', 'username': 'new-regular-user', 'password1': 'one', 'password2': 'two',
            'first_name': '<script>alert(1)</script>', 'last_name': 'Test', 'email': 'example@example.test',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['type_form'], 'register')
        self.assertEqual(response.context['next'], destination)
        self.assertEqual(get_user_model().objects.count(), before)
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertTrue(response.context['register_form'].errors['password2'])
        self.assertContains(response, 'aria-describedby="alerts-container"')

    def test_login_and_registration_keep_success_redirects_and_account_fields(self):
        destination = '/habitus/?from=public&step=first'
        entry = reverse('entry') + '?' + urlencode({'next': destination})
        response = self.client.post(entry, {'login': '', 'username': self.user.username,
                                           'password': 'Only-Local-Habits-47!'})
        self.assertRedirects(response, destination, fetch_redirect_response=False)
        self.client.logout()
        response = self.client.post(entry, {'register': '', 'username': 'new-public-user',
            'password1': 'Local-Habits-Only-81!', 'password2': 'Local-Habits-Only-81!',
            'first_name': 'Test', 'last_name': 'Account', 'email': 'new@example.test'})
        self.assertRedirects(response, destination, fetch_redirect_response=False)
        user = get_user_model().objects.get(username='new-public-user')
        self.assertEqual((user.first_name, user.last_name, user.email), ('Test', 'Account', 'new@example.test'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_default_login_and_logout_redirect_to_named_home(self):
        response = self.client.post(reverse('entry'), {'login': '', 'username': self.user.username,
                                                       'password': 'Only-Local-Habits-47!'})
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse('entry')), '/', fetch_redirect_response=False)
        self.assertRedirects(self.client.post(reverse('logout')), '/', fetch_redirect_response=False)

    def test_registration_and_login_keep_csrf_enforcement(self):
        client = Client(enforce_csrf_checks=True)
        for mode, data in (('login', {'login': '', 'username': self.user.username, 'password': 'Only-Local-Habits-47!'}),
                           ('register', {'register': '', 'username': 'csrf-public-user',
                                         'password1': 'Local-Habits-Only-81!', 'password2': 'Local-Habits-Only-81!'})):
            entry = reverse('entry') + '?type=' + mode
            self.assertEqual(client.post(entry, data).status_code, 403)
            client.get(entry)
            response = client.post(entry, data, HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
            self.assertEqual(response.status_code, 302)
            client.logout()

    @override_settings(DEBUG=False)
    def test_real_404_keeps_status_and_does_not_canonicalize_missing_urls(self):
        for signed_in in (False, True):
            if signed_in:
                self.client.force_login(self.user)
            response = self.client.get('/missing/<script>private-input</script>/')
            self.assertEqual(response.status_code, 404)
            self.assertTemplateUsed(response, '404.html')
            self.assertNotIn('Location', response)
            self.assertContains(response, 'Страница не найдена', status_code=404)
            self.assertNotContains(response, 'private-input', status_code=404)
            self.assertNotContains(response, 'rel="canonical"', status_code=404)
            self.assertNotContains(response, 'Traceback', status_code=404)
            self.assertContains(response, '<a class="public-button" href="/">', status_code=404)

    def test_tracker_and_admin_do_not_receive_the_public_layer(self):
        self.client.force_login(self.user)
        for path in (reverse('by_date', args=['2026-10']), reverse('admin:login')):
            response = self.client.get(path, HTTP_HOST='testserver')
            self.assertEqual(response.status_code, 200)
            for marker in ('data-public-theme=', 'public-theme.js', 'general_app/css/public.css', 'productivum.publicTheme'):
                self.assertNotContains(response, marker)

    def test_shared_navbar_keeps_guest_and_member_links_and_adds_home(self):
        for signed_in, sections in ((False, ['home', 'register', 'login', 'about']),
                                   (True, ['home', 'habitus', 'profile', 'about'])):
            if signed_in:
                self.client.force_login(self.user)
            response = self.client.get('/')
            elements = PageElements(response)
            links = [a for a in elements.tags('a') if 'data-section' in a]
            self.assertEqual([a['data-section'] for a in links], sections)
            home = next(a for a in links if a['data-section'] == 'home')
            self.assertEqual(home['href'], reverse('home'))
            self.assertEqual(home['aria-current'], 'page')
            self.assertNotContains(response, 'id="buttonSettings"')
        tracker = self.client.get(reverse('by_date', args=['2026-10']), HTTP_HOST='testserver')
        elements = PageElements(tracker)
        self.assertEqual([a['data-section'] for a in elements.tags('a') if 'data-section' in a],
                         ['home', 'habitus', 'profile', 'about'])
        self.assertContains(tracker, 'id="buttonSettings" type="button"')
        self.assertContains(tracker, "document.getElementById('some-modal-id').showModal();")
        self.assertNotContains(tracker, 'data-public-theme-control')

    def test_about_keeps_existing_content_and_non_home_urls_do_not_redirect(self):
        response = self.client.get(reverse('about'))
        for text in ('Дмитрий', 'Ярославле', 'ЯГТУ', '1С', 'Благодарности', 'Ари', 'hwyd.me', 'JimHoleInOne'):
            self.assertContains(response, text)
        for path in ('/home/unknown/', '/some-other-page/', '/about'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn('Location', response)
