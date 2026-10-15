"""The themed profile keeps its auth, form and error presentation contracts."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .test_public_pages import PageElements


class ProfilePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('profile-page', password='Original-Profile-Only-47!')

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse('profile')

    def test_profile_uses_shared_theme_and_keeps_all_four_post_forms_and_labels(self):
        self.assertRedirects(Client().get(self.url), reverse('entry') + '?next=' + self.url,
                             fetch_redirect_response=False)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'general_app/public_base.html')
        self.assertContains(response, 'data-public-theme="auto"')
        self.assertContains(response, 'productivum.publicTheme')
        elements = PageElements(response)
        self.assertEqual(len(elements.tags('h1')), 1)
        self.assertEqual(len(elements.tags('main')), 1)
        self.assertEqual(len(elements.tags('nav')), 1)
        self.assertEqual(len([b for b in elements.tags('button') if 'data-public-theme-control' in b]), 1)
        self.assertEqual([s['src'] for s in elements.tags('script') if s.get('src')],
                         ['/static/general_app/js/public-theme.js?v=20261015'])
        styles = [el['href'] for el in elements.tags('link') if el.get('rel') == 'stylesheet']
        self.assertLess(next(i for i, url in enumerate(styles) if '/public.css?' in url),
                        next(i for i, url in enumerate(styles) if '/profile.css?' in url))
        forms = {f['id']: f for f in elements.tags('form')}
        self.assertEqual(set(forms), {'profile-avatar-form', 'profile-user-form',
                                      'profile-password-form', 'profile-logout-form'})
        for name, form in forms.items():
            self.assertEqual(form['method'], 'post')
            self.assertEqual(form['action'], reverse('logout') if name == 'profile-logout-form' else self.url)
        self.assertEqual(forms['profile-avatar-form']['enctype'], 'multipart/form-data')
        self.assertEqual(sum(i.get('name') == 'csrfmiddlewaretoken' for i in elements.tags('input')), 4)
        labels = {label['for'] for label in elements.tags('label')}
        fields = {field['name']: field for field in elements.tags('input')}
        for name, autocomplete in {'username': 'username', 'first_name': 'given-name', 'last_name': 'family-name',
                                   'email': 'email', 'old_password': 'current-password',
                                   'new_password1': 'new-password', 'new_password2': 'new-password'}.items():
            self.assertEqual(fields[name]['autocomplete'], autocomplete)
            self.assertIn(fields[name]['id'], labels)
        self.assertEqual(fields['profile_action']['value'], 'avatar')
        self.assertContains(response, 'href="#change-password-section"')
        self.assertContains(response, 'href="#edit-profile-section"')
        self.assertNotContains(response, 'style="display:none;"')

    def test_invalid_profile_keeps_values_and_renders_real_error_description_targets(self):
        response = self.client.post(self.url, {'username': 'invalid username!', 'first_name': '<script>unsafe()</script>',
                                               'last_name': 'Example', 'email': 'example@example.test'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user_form'].errors['username'])
        self.assertFalse(response.context['password_form'].is_bound)
        elements = PageElements(response)
        field = next(field for field in elements.tags('input') if field.get('name') == 'username')
        self.assertEqual(field['value'], 'invalid username!')
        self.assertEqual(field['aria-invalid'], 'true')
        ids = [attrs.get('id') for _, attrs in elements.elements]
        for target in field['aria-describedby'].split():
            self.assertEqual(ids.count(target), 1)
        self.assertContains(response, '&lt;script&gt;unsafe()&lt;/script&gt;')
        self.assertNotContains(response, '<script>unsafe()</script>')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'profile-page')

    def test_password_error_selects_password_view_without_changing_credentials_or_session(self):
        response = self.client.post(self.url, {'old_password': 'incorrect', 'new_password1': 'Synthetic-New-Only-92!',
                                               'new_password2': 'Synthetic-New-Only-92!'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['password_form'].errors['old_password'])
        self.assertContains(response, 'data-password-errors="true"')
        elements = PageElements(response)
        fields = {field['name']: field for field in elements.tags('input')}
        self.assertEqual(fields['old_password']['aria-invalid'], 'true')
        self.assertIn('id_old_password_error', fields['old_password']['aria-describedby'].split())
        self.assertContains(response, 'id="id_old_password_error"')
        for name in ('old_password', 'new_password1', 'new_password2'):
            self.assertNotIn('value', fields[name])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original-Profile-Only-47!'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_stats_visibility_and_csrf_are_preserved(self):
        self.assertNotContains(self.client.get(self.url), reverse('activity_users'))
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.assertContains(self.client.get(self.url), 'href="' + reverse('activity_users') + '"')
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(self.url, {'email': 'example@example.test'}).status_code, 403)
        self.assertEqual(protected.post(reverse('logout')).status_code, 403)
