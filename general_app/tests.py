import json
import re
import subprocess
from io import BytesIO
from tempfile import TemporaryDirectory
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.http import HttpResponse
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe
from .models import UserProfile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, Resolver404, resolve, reverse


class ProfilePhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='photo-user', password='Original-strong-password-42')
        cls.other = get_user_model().objects.create_user(username='photo-other')
        cls.video_fixtures = {}
        with TemporaryDirectory(prefix='habitus-webm-fixtures-') as directory:
            for name, duration, video in [('valid', '0.5', True), ('long', '11', True), ('audio', '0.5', False)]:
                target = Path(directory) / f'{name}.webm'
                command = [get_ffmpeg_exe(), '-nostdin', '-v', 'error']
                if video:
                    command += ['-f', 'lavfi', '-i', 'testsrc2=size=64x48:rate=30']
                command += ['-f', 'lavfi', '-i', 'sine=frequency=440', '-t', duration]
                if video:
                    command += ['-c:v', 'libvpx-vp9', '-threads', '1', '-deadline', 'realtime']
                command += ['-c:a', 'libopus', '-metadata', 'title=untrusted metadata', '-y', str(target)]
                subprocess.run(command, check=True, capture_output=True, timeout=20,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                cls.video_fixtures[name] = target.read_bytes()

    def setUp(self):
        media = TemporaryDirectory(prefix='productivum-avatar-test-')
        self.media = Path(media.name)
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.user)
        self.url = reverse('profile')

    def photo(self, image_format='PNG', color='blue', suffix=None):
        output = BytesIO()
        Image.new('RGB', (32, 24), color).save(output, format=image_format)
        extension = suffix or {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif', 'BMP': 'bmp'}[image_format]
        return SimpleUploadedFile(f'photo.{extension}', output.getvalue(), content_type='application/octet-stream')

    def upload(self, image=None, **extra):
        return self.client.post(self.url, {'profile_action': 'avatar', 'avatar': image or self.photo(), **extra})

    def test_supported_photos_are_saved_owned_and_displayed_after_reload(self):
        for image_format in ('PNG', 'JPEG', 'WEBP', 'GIF'):
            with self.subTest(image_format=image_format), self.captureOnCommitCallbacks(execute=True):
                response = self.upload(self.photo(image_format))
                self.assertRedirects(response, self.url)
                profile = UserProfile.objects.get(user=self.user)
                self.assertTrue(profile.avatar.storage.exists(profile.avatar.name))
                self.assertTrue(profile.avatar.name.startswith(f'profiles/{self.user.pk}/'))
                self.assertFalse(Path(profile.avatar.name).is_absolute())
                with profile.avatar.open('rb') as stored, Image.open(stored) as image:
                    self.assertEqual(image.format, image_format)
                    image.load()
                for _ in range(2):
                    self.assertContains(self.client.get(self.url), profile.avatar.url)

    def test_replacement_updates_one_profile_and_removes_old_file(self):
        self.upload()
        old = UserProfile.objects.get(user=self.user).avatar.name
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.upload(self.photo(color='red')), self.url)
        profile = UserProfile.objects.get(user=self.user)
        self.assertNotEqual(profile.avatar.name, old)
        self.assertFalse(profile.avatar.storage.exists(old))
        self.assertTrue(profile.avatar.storage.exists(profile.avatar.name))
        self.assertEqual(UserProfile.objects.filter(user=self.user).count(), 1)

    def test_development_media_route_serves_from_configured_storage(self):
        from importlib.util import module_from_spec, spec_from_file_location
        self.upload()
        avatar = UserProfile.objects.get(user=self.user).avatar
        spec = spec_from_file_location('profile_media_test_urls', Path(__file__).resolve().parent.parent / 'my_site' / 'urls.py')
        urlconf = module_from_spec(spec)
        with self.settings(DEBUG=True):
            spec.loader.exec_module(urlconf)
        match = resolve(avatar.url, urlconf=urlconf)
        self.assertEqual(Path(match.kwargs['document_root']), self.media)
        response = match.func(RequestFactory().get(avatar.url), *match.args, **match.kwargs)
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'image/png')
            self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG'))
        finally:
            response.close()
        production_urlconf = module_from_spec(spec)
        with self.settings(DEBUG=False):
            spec.loader.exec_module(production_urlconf)
        with self.assertRaises(Resolver404):
            resolve(avatar.url, urlconf=production_urlconf)

    def test_fake_corrupt_and_unsupported_images_are_form_errors(self):
        cases = (
            SimpleUploadedFile('fake.jpg', b'<html>not a photo</html>', content_type='image/jpeg'),
            SimpleUploadedFile('bad.png', b'\x89PNG\r\n\x1a\n', content_type='image/png'),
            self.photo('BMP', suffix='png'),
            SimpleUploadedFile('vector.svg', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', content_type='image/png'),
        )
        for image in cases:
            with self.subTest(filename=image.name):
                response = self.upload(image)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['photo_form'].errors.get('avatar'))
        self.assertFalse(UserProfile.objects.filter(user=self.user).exists())
        self.assertEqual(list(self.media.rglob('*')), [])

    def test_oversized_upload_is_rejected_before_decoding(self):
        image = SimpleUploadedFile('large.png', b'x' * (5 * 1024 * 1024 + 1), content_type='image/png')
        response = self.upload(image)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Размер фотографии не должен превышать 5 МБ.')
        self.assertFalse(UserProfile.objects.exists())

    def animation(self, durations=(100, 200, 300)):
        output = BytesIO()
        frames = [Image.new('RGBA', (32, 24), color) for color in ('red', 'green', 'blue')]
        frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:],
                       duration=list(durations), loop=0, comment=b'untrusted metadata')
        return SimpleUploadedFile('animation.png', output.getvalue(), content_type='image/png')

    def test_gif_preserves_frames_timing_and_loop_without_metadata(self):
        self.assertRedirects(self.upload(self.animation()), self.url)
        avatar = UserProfile.objects.get(user=self.user).avatar
        self.assertTrue(avatar.name.endswith('.gif'))
        with avatar.open('rb') as stored, Image.open(stored) as image:
            self.assertEqual(image.n_frames, 3)
            self.assertEqual(image.info['loop'], 0)
            self.assertNotIn('comment', image.info)
            colors, durations = [], []
            for index in range(3):
                image.seek(index)
                durations.append(image.info['duration'])
                colors.append(image.convert('RGB').getpixel((0, 0)))
            self.assertEqual(durations, [100, 200, 300])
            self.assertEqual(colors, [(255, 0, 0), (0, 128, 0), (0, 0, 255)])
        self.assertNotContains(self.client.get(self.url), '<video')

    def test_long_gif_is_rejected(self):
        response = self.upload(self.animation((4000, 4000, 4000)))
        self.assertContains(response, 'Длительность анимации не должна превышать 10 секунд.')
        self.assertFalse(UserProfile.objects.exists())

    def test_gif_preserves_transparency(self):
        output = BytesIO()
        frame = Image.new('RGBA', (32, 24), (0, 0, 0, 0))
        frame.paste((255, 0, 0, 255), (8, 8, 16, 16))
        frame.save(output, format='GIF')
        self.assertRedirects(self.upload(SimpleUploadedFile('transparent.gif', output.getvalue())), self.url)
        with UserProfile.objects.get(user=self.user).avatar.open('rb') as stored, Image.open(stored) as image:
            self.assertEqual(image.convert('RGBA').getpixel((0, 0))[3], 0)
            self.assertEqual(image.convert('RGBA').getpixel((10, 10)), (255, 0, 0, 255))

    def test_webm_is_decoded_normalized_muted_and_displayed(self):
        upload = SimpleUploadedFile('video.jpg', self.video_fixtures['valid'])
        self.assertRedirects(self.upload(upload), self.url)
        profile = UserProfile.objects.get(user=self.user)
        self.assertTrue(profile.avatar_is_video)
        self.assertTrue(profile.avatar.name.endswith('.webm'))
        with profile.avatar.open('rb') as stored:
            self.assertNotIn(b'untrusted metadata', stored.read())
        # Decode the actual stored result, and verify the audio stream was removed.
        result = subprocess.run([get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-i', profile.avatar.path,
                                 '-f', 'null', '-'], capture_output=True, timeout=20,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'Video: vp9', result.stderr)
        self.assertNotIn(b'Audio:', result.stderr)
        for _ in range(2):
            response = self.client.get(self.url)
            self.assertContains(response, f'<video src="{profile.avatar.url}" autoplay loop muted playsinline')

    def test_invalid_webm_is_rejected_without_touching_previous_avatar(self):
        self.upload()
        old_name = UserProfile.objects.get(user=self.user).avatar.name
        for content in (b'not a video', b'\x1a\x45\xdf\xa3bad header',
                        self.video_fixtures['valid'][:120], self.video_fixtures['valid'][:-100],
                        self.video_fixtures['audio'], self.video_fixtures['long']):
            with self.subTest(length=len(content)):
                response = self.upload(SimpleUploadedFile('invalid.webm', content, content_type='video/webm'))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['photo_form'].errors.get('avatar'))
                self.assertEqual(UserProfile.objects.get(user=self.user).avatar.name, old_name)
        self.assertEqual(len(list(self.media.rglob('*.*'))), 1)

    def test_webm_decoder_timeout_is_a_form_error(self):
        from unittest.mock import patch
        with patch('general_app.avatar.subprocess.run', side_effect=subprocess.TimeoutExpired('ffmpeg', 20)):
            response = self.upload(SimpleUploadedFile('video.webm', self.video_fixtures['valid']))
        self.assertContains(response, 'Обработка WEBM заняла слишком много времени.')
        self.assertFalse(UserProfile.objects.exists())

    def test_replacing_photo_with_video_and_back_removes_previous_files(self):
        self.upload(self.animation())
        for upload in (SimpleUploadedFile('avatar.webm', self.video_fixtures['valid']), self.photo()):
            old_name = UserProfile.objects.get(user=self.user).avatar.name
            with self.captureOnCommitCallbacks(execute=True):
                self.assertRedirects(self.upload(upload), self.url)
            profile = UserProfile.objects.get(user=self.user)
            self.assertFalse(profile.avatar.storage.exists(old_name))
            self.assertTrue(profile.avatar.storage.exists(profile.avatar.name))

    def test_high_resolution_is_rejected_even_when_file_is_small(self):
        output = BytesIO()
        with Image.new('RGB', (5000, 4001), 'white') as image:
            image.save(output, format='PNG')
        response = self.upload(SimpleUploadedFile('large-resolution.png', output.getvalue()))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Разрешение фотографии не должно превышать 20 млн пикселей.')
        self.assertFalse(UserProfile.objects.exists())

    def test_payload_and_filename_are_normalized_from_verified_pixels(self):
        photo = self.photo('JPEG', suffix='png')
        photo = SimpleUploadedFile('untrusted.png', photo.read() + b'<script>unexpected payload</script>')
        self.upload(photo)
        avatar = UserProfile.objects.get(user=self.user).avatar
        self.assertTrue(avatar.name.endswith('.jpg'))
        with avatar.open('rb') as stored:
            self.assertNotIn(b'unexpected payload', stored.read())

    def test_forged_user_ids_do_not_change_another_users_photo(self):
        self.client.force_login(self.other)
        self.upload(self.photo(color='green'))
        foreign = UserProfile.objects.get(user=self.other)
        old_name = foreign.avatar.name
        self.client.force_login(self.user)
        self.upload(user=self.other.pk, user_id=self.other.pk, profile_id=foreign.pk, pk=foreign.pk)
        foreign.refresh_from_db()
        self.assertEqual(foreign.avatar.name, old_name)
        self.assertTrue(foreign.avatar.storage.exists(old_name))
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_anonymous_and_missing_csrf_cannot_upload(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {'profile_action': 'avatar', 'avatar': self.photo()}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.upload().status_code, 302)
        self.assertFalse(UserProfile.objects.exists())
        self.assertEqual(list(self.media.rglob('*')), [])

    def test_invalid_replacement_preserves_existing_photo(self):
        self.upload()
        old_name = UserProfile.objects.get(user=self.user).avatar.name
        response = self.upload(SimpleUploadedFile('invalid.jpg', b'bad image'))
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.avatar.name, old_name)
        self.assertContains(response, profile.avatar.url)

    def test_profile_without_photo_keeps_user_and_password_flows(self):
        self.assertContains(self.client.get(self.url), 'enctype="multipart/form-data"')
        self.assertFalse(UserProfile.objects.exists())
        self.assertRedirects(self.client.post(self.url, {
            'username': self.user.username, 'first_name': 'Мария', 'last_name': '', 'email': 'test@example.com',
        }), self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Мария')
        self.assertRedirects(self.client.post(self.url, {
            'old_password': 'Original-strong-password-42', 'new_password1': 'New-strong-password-73',
            'new_password2': 'New-strong-password-73',
        }), self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('New-strong-password-73'))
        self.assertEqual(self.client.get(self.url).status_code, 200)


class RemovedSectionsTests(SimpleTestCase):
    def test_removed_urls_do_not_resolve(self):
        for path in ('/todos/', '/todos/2026-09-30/', '/todos/add/',
                     '/todos/1/update/', '/todos/1/delete/', '/todos/load-todos/',
                     '/pomodoro/', '/home/math/', '/home/math/results/'):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_removed_names_cannot_be_reversed(self):
        for name in ('todos:index', 'todos:add', 'pomodoro:base',
                     'mathtraining', 'math_training_results'):
            with self.subTest(name=name), self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_archive_is_not_discovered_by_apps_templates_or_static(self):
        self.assertFalse(apps.is_installed('todos'))
        self.assertFalse(apps.is_installed('pomodoro'))
        self.assertFalse(any(app.name.startswith('archive') for app in apps.get_app_configs()))
        for name in ('todos/base.html', 'todos/index.html', 'pomodoro/index.html',
                     'general_app/mathtraining.html', 'general_app/mathtraining_results.html',
                     'archive/math/templates/general_app/mathtraining.html'):
            with self.subTest(template=name), self.assertRaises(TemplateDoesNotExist):
                get_template(name)
        for path in ('main.css', 'pomodoro/main.css', 'pomodoro/main.js',
                     'pomodoro/modal.css', 'end.mp3', 'font-awesome.min.css',
                     'general_app/css/math-main.css', 'general_app/css/math-result-main.css'):
            with self.subTest(static=path):
                self.assertIsNone(finders.find(path))
        self.assertIsNotNone(finders.find('hwyd/css/main.css'))
        self.assertIsNotNone(finders.find('hwyd/vendor/font-awesome/css/font-awesome.min.css'))


class StaticServingTests(SimpleTestCase):
    @override_settings(DEBUG=True)
    def test_local_whitenoise_serves_namespaced_source_without_collection(self):
        from whitenoise.middleware import WhiteNoiseMiddleware

        middleware = WhiteNoiseMiddleware(lambda request: HttpResponse(status=404))
        for asset in ('hwyd/css/main.css', 'chat/js/chat.js', 'site/css/navbar.css',
                      'notifications/css/modal.css', 'hwyd/css/dialogs.css',
                      'hwyd/js/toolbar.js', 'hwyd/js/theme-schedule.js', 'hwyd/js/dialog-drag.js'):
            with self.subTest(asset=asset):
                response = middleware(RequestFactory().get('/static/' + asset))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content),
                                 Path(finders.find(asset)).read_bytes())
                response.close()


class RemainingPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username='remaining-pages')

    def assert_removed_links_absent(self, response):
        for fragment in ('/todos/', '/pomodoro/', '/home/math/',
                         'id="todoapp"', 'id="pomodorotimer"', 'id="mathtraining"'):
            self.assertNotContains(response, fragment)

    def test_public_pages_render_and_keep_authentication_links(self):
        for name in ('home', 'about', 'entry'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assert_removed_links_absent(response)
                self.assertContains(response, reverse('entry'))
        self.assertEqual(self.client.get(reverse('profile')).status_code, 302)

    def test_authenticated_pages_keep_habitus_profile_and_notifications(self):
        from notifications.models import Notification

        Notification.objects.create(title='Remaining notification', message='Still available')
        self.client.force_login(self.user)
        for name in ('home', 'about', 'profile'):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assert_removed_links_absent(response)
                self.assertContains(response, reverse('index'))
                self.assertContains(response, reverse('profile'))
                self.assertContains(response, 'Remaining notification')

    def test_habitus_renders_desktop_and_mobile_with_chat(self):
        from notifications.models import Notification

        Notification.objects.create(message='Habitus notification')
        self.client.force_login(self.user)
        agents = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
            'AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1',
        )
        for agent in agents:
            with self.subTest(agent=agent):
                response = self.client.get(reverse('by_date', args=['2026-09']),
                                           HTTP_USER_AGENT=agent, HTTP_HOST='testserver')
                self.assertEqual(response.status_code, 200)
                self.assert_removed_links_absent(response)
                self.assertContains(response, reverse('chat:messages'))
                self.assertContains(response, reverse('notifications:mark-seen'))

    def test_notification_mark_seen_still_works(self):
        from notifications.models import Notification, NotificationSeen

        notification = Notification.objects.create(message='Test notification')
        url = reverse('notifications:mark-seen')
        self.assertEqual(self.client.post(url, {'id': notification.pk}).status_code, 403)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url, {'id': notification.pk}).status_code, 200)
        self.assertTrue(NotificationSeen.objects.filter(notification=notification, user=self.user).exists())

    def test_rendered_pages_resolve_their_local_static_dependencies(self):
        from general_app.models import Guide
        from notifications.models import Notification

        Guide.objects.create(slug='main_toolbar', title='Toolbar')
        Notification.objects.create(message='Static dependency fixture')
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.client.force_login(self.user)
        paths = [reverse(name) for name in ('home', 'about', 'profile',
                                            'edit_settings', 'activity_users')]
        paths.append(reverse('by_date', args=['2026-09']))
        for path in paths:
            with self.subTest(page=path):
                response = self.client.get(path, HTTP_HOST='testserver')
                self.assertEqual(response.status_code, 200)
                assets = re.findall(r'(?:href|src)="/static/([^"?]+)',
                                    response.content.decode())
                self.assertTrue(assets)
                for asset in assets:
                    with self.subTest(asset=asset):
                        self.assertIsNotNone(finders.find(asset))

    def test_manifest_and_service_worker_keep_routes_and_resolve_icons(self):
        manifest = json.loads(Path(finders.find('hwyd/manifest_habitus.json')).read_text())
        self.assertEqual(manifest['start_url'], '/habitus')
        for icon in manifest['icons']:
            self.assertIsNotNone(finders.find(icon['src'].removeprefix('/static/')))
        response = self.client.get(reverse('service_worker'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')
        for asset in re.findall(r'/static/([^\s\x27\"]+)', response.content.decode()):
            self.assertIsNotNone(finders.find(asset))
