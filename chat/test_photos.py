import json
import subprocess
from functools import lru_cache
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, DatabaseError
from django.db.migrations.executor import MigrationExecutor
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from .models import ChatMessage, ChatReadState, ChatAttachment
from .photos import MAX_PHOTO_BYTES


@lru_cache(maxsize=4)
def webm_sample(duration='1', audio=True):
    from imageio_ffmpeg import get_ffmpeg_exe
    with TemporaryDirectory(prefix='chat-webm-fixture-') as directory:
        path = Path(directory) / 'sample.webm'
        command = [get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                   '-f', 'lavfi', '-i', 'testsrc2=size=160x80:rate=30']
        if audio:
            command += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000']
        command += ['-t', duration, '-c:v', 'libvpx-vp9', '-threads', '1', '-deadline', 'realtime',
                    '-cpu-used', '8', '-c:a', 'libopus', '-metadata', 'title=private-fixture', str(path)]
        subprocess.run(command, check=True, capture_output=True, timeout=20,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return path.read_bytes()


@lru_cache(maxsize=2)
def transparent_webm_sample(codec):
    from imageio_ffmpeg import get_ffmpeg_exe
    with TemporaryDirectory(prefix='chat-alpha-fixture-') as directory:
        source, target = Path(directory) / 'source.png', Path(directory) / 'sample.webm'
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        image.paste((220, 60, 20, 255), (16, 16, 32, 48))
        image.paste((20, 100, 200, 128), (32, 16, 48, 48))
        image.save(source)
        subprocess.run([
            get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
            '-loop', '1', '-i', str(source), '-t', '0.3', '-c:v', codec,
            '-threads', '1', '-auto-alt-ref', '0', '-pix_fmt', 'yuva420p', str(target),
        ], check=True, capture_output=True, timeout=20,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return target.read_bytes()


@override_settings(MIDDLEWARE=[
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
])
class ChatPhotoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user('photo-owner', is_superuser=True, is_staff=False)
        cls.member = get_user_model().objects.create_user('photo-member')
        cls.staff = get_user_model().objects.create_user('photo-staff', is_staff=True)

    def setUp(self):
        directory = TemporaryDirectory(prefix='productivum-chat-photo-test-')
        self.root = Path(directory.name)
        self.addCleanup(directory.cleanup)
        override = override_settings(CHAT_PHOTO_ROOT=self.root / 'private', MEDIA_ROOT=self.root / 'public')
        override.enable()
        self.addCleanup(override.disable)
        self.client.force_login(self.owner)
        self.url = reverse('chat:messages')

    def photo(self, format='PNG', size=(32, 16), **options):
        output = BytesIO()
        Image.new('RGB', size, 'blue').save(output, format=format, **options)
        return SimpleUploadedFile('untrusted.name', output.getvalue(), content_type='application/octet-stream')

    def files(self):
        return list(self.root.rglob('*.*'))

    def upload(self, photo=None, client=None, **data):
        return (client or self.client).post(self.url, {'photo': photo or self.photo(), **data})

    def allow_send(self):
        ChatReadState.objects.filter(user=self.owner).update(last_sent_at=timezone.now() - timedelta(seconds=3))

    def test_owner_with_or_without_text_supported_formats_and_untrusted_metadata(self):
        for format in ('JPEG', 'PNG', 'WEBP'):
            with self.subTest(format=format):
                self.allow_send()
                response = self.upload(self.photo(format), text=' Подпись <b>буквально</b> ' if format == 'JPEG' else '')
                self.assertEqual(response.status_code, 201)
                message = ChatMessage.objects.get(pk=response.json()['message']['id'])
                self.assertEqual(message.sender, self.owner)
                self.assertEqual(message.text, 'Подпись <b>буквально</b>' if format == 'JPEG' else '')
                self.assertRegex(message.photo.name, r'\A[0-9a-f]{32}\.(jpg|png|webp)\Z')
                self.assertTrue(message.photo.storage.exists(message.photo.name))
                with self.assertRaises(ValueError):
                    message.photo.url
                url = response.json()['message']['photo']['url']
                self.client.force_login(self.member)
                stored = self.client.get(url)
                self.assertEqual(stored.status_code, 200)
                self.assertIn('no-store', stored['Cache-Control'])
                self.assertEqual(stored['X-Content-Type-Options'], 'nosniff')
                content = b''.join(stored.streaming_content)
                stored.close()
                with Image.open(BytesIO(content)) as decoded:
                    self.assertEqual(decoded.format, format)
                    self.assertEqual(decoded.size, (32, 16))
                self.assertEqual(Client().get(url).status_code, 401)
                self.assertEqual(self.client.get('/media/' + message.photo.name).status_code, 404)
                self.client.force_login(self.owner)

    def test_non_owner_staff_and_anonymous_cannot_upload_or_forge_roles(self):
        for user in (self.member, self.staff):
            self.client.force_login(user)
            self.assertEqual(self.upload(user_id=self.owner.pk, is_superuser='true').status_code, 403)
        self.assertEqual(self.upload(client=Client()).status_code, 401)
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatReadState.objects.exists())
        self.assertEqual(self.files(), [])

    def test_corrupt_spoofed_and_unsupported_files_leave_no_message_or_file(self):
        png = self.photo().read()
        invalid = [
            SimpleUploadedFile('fake.jpg', b'<html>not a photo</html>', content_type='image/jpeg'),
            SimpleUploadedFile('fake.png', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', content_type='image/png'),
            self.photo('BMP'), self.photo('GIF'),
            SimpleUploadedFile('broken.png', png[:45], content_type='image/png'),
        ]
        for photo in invalid:
            with self.subTest(name=photo.name):
                self.assertEqual(self.upload(photo).status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatReadState.objects.exists())
        self.assertEqual(self.files(), [])

    def test_file_size_boundary_is_real_and_checked_before_image_decode(self):
        content = self.photo().read()
        boundary = content + b'\0' * (MAX_PHOTO_BYTES - len(content))
        self.assertEqual(self.upload(SimpleUploadedFile('photo.png', boundary)).status_code, 201)
        self.allow_send()
        with patch('chat.photos.Image.open', side_effect=AssertionError('must not decode oversized upload')):
            rejected = self.upload(SimpleUploadedFile('photo.png', boundary + b'0'))
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(len(self.files()), 1)

    def test_pixel_boundary_and_oversized_dimensions(self):
        self.assertEqual(self.upload(self.photo(size=(5000, 4000))).status_code, 201)
        self.allow_send()
        oversized = self.photo(size=(5000, 4001))
        with patch('PIL.Image.Image.load', side_effect=AssertionError('must reject dimensions before decoding')):
            response = self.upload(oversized)
        self.assertEqual(response.status_code, 400)
        self.assertIn('20', response.json()['error'])
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(len(self.files()), 1)

    def test_orientation_and_metadata_are_normalized_and_payload_removed(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'private author'
        photo = self.photo('JPEG', size=(40, 20), exif=exif)
        source = photo.read() + b'<script>untrusted trailer</script>'
        response = self.upload(SimpleUploadedFile('../../video.webm', source, content_type='image/jpeg'))
        self.assertEqual(response.status_code, 201)
        message = ChatMessage.objects.get()
        with message.photo.open('rb') as file:
            data = file.read()
        self.assertNotIn(b'<script>', data)
        self.assertNotIn(b'private author', data)
        with Image.open(BytesIO(data)) as normalized:
            self.assertEqual(normalized.size, (20, 40))
            self.assertFalse(normalized.getexif())

    def test_animation_and_unknown_file_fields_rejected(self):
        output = BytesIO()
        Image.new('RGB', (12, 12), 'blue').save(output, format='PNG', save_all=True,
                                              append_images=[Image.new('RGB', (12, 12), 'red')])
        self.assertEqual(self.upload(SimpleUploadedFile('animation.png', output.getvalue())).status_code, 400)
        self.assertEqual(self.client.post(self.url, {'photo': self.photo(), 'extra': self.photo()}).status_code, 400)
        self.assertEqual(self.files(), [])
        self.assertFalse(ChatMessage.objects.exists())

    def test_csrf_and_cooldown_preserved_for_photo(self):
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.owner)
        self.assertEqual(self.upload(client=secured).status_code, 403)
        self.assertEqual(self.files(), [])
        request = RequestFactory().get('/')
        token = get_token(request)
        secured.cookies['csrftoken'] = request.META['CSRF_COOKIE']
        self.assertEqual(secured.post(self.url, {'photo': self.photo()}, HTTP_X_CSRFTOKEN=token).status_code, 201)
        limited = self.upload()
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited['Retry-After'], '2')
        self.assertEqual(len(self.files()), 1)
        self.assertEqual(ChatMessage.objects.count(), 1)

    def test_storage_and_database_failures_roll_back_cooldown_and_clean_files(self):
        storage = ChatAttachment._meta.get_field('file').storage
        original_save = storage._save
        def partial_write(name, content):
            original_save(name, content)
            raise OSError('write failed')
        with patch.object(storage, '_save', side_effect=partial_write):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.files(), [])
        self.assertFalse(ChatMessage.objects.exists())
        self.assertIsNone(ChatReadState.objects.get(user=self.owner).last_sent_at)
        with patch.object(ChatMessage, 'save', side_effect=DatabaseError('insert failed')):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.files(), [])
        self.assertFalse(ChatMessage.objects.exists())
        self.assertIsNone(ChatReadState.objects.get(user=self.owner).last_sent_at)
        self.assertEqual(self.upload().status_code, 201)

    def test_history_polling_replies_and_caption_edit(self):
        first = self.upload().json()['message']
        self.allow_send()
        reply = self.upload(text='Ответ', reply_to=first['id']).json()['message']
        self.assertTrue(reply['reply_to']['has_photo'])
        self.assertEqual(reply['reply_to']['text'], '')
        message = ChatMessage.objects.get(pk=first['id'])
        url = reverse('chat:message', args=[message.pk])
        self.assertEqual(self.client.patch(url, json.dumps({'text': ''}), content_type='application/json').status_code, 200)
        initial = self.client.get(self.url).json()['messages']
        incremental = self.client.get(self.url, {'after_id': first['id']}).json()['messages']
        self.assertIsNotNone(initial[0]['photo'])
        self.assertIsNotNone(incremental[0]['photo'])
        self.client.force_login(self.member)
        self.assertEqual(self.client.patch(url, json.dumps({'text': 'forged'}), content_type='application/json').status_code, 403)
        response = self.client.post(self.url, json.dumps({'text': 'Plain', 'photo': {'url': 'https://evil.invalid'}}), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.json()['message']['photo'])
        self.assertEqual(self.client.post(self.url, json.dumps({'text': ''}), content_type='application/json').status_code, 400)

    def test_deleted_photos_are_inaccessible_and_removed_after_commit_and_cascade(self):
        message = ChatMessage.objects.get(pk=self.upload().json()['message']['id'])
        self.client.force_login(self.member)
        self.assertEqual(self.client.delete(reverse('chat:message', args=[message.pk])).status_code, 403)
        self.client.force_login(self.owner)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(reverse('chat:message', args=[message.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('chat:photo', args=[message.pk])).status_code, 404)
        self.assertEqual(self.files(), [])
        self.allow_send()
        self.upload()
        with self.captureOnCommitCallbacks(execute=True):
            self.owner.delete()
        self.assertEqual(self.files(), [])

    def test_list_query_count_does_not_grow_per_photo(self):
        message = ChatMessage.objects.get(pk=self.upload().json()['message']['id'])
        with CaptureQueriesContext(connection) as single:
            self.assertEqual(self.client.get(self.url).status_code, 200)
        for index in range(10):
            item = ChatMessage.objects.create(sender=self.owner, text=str(index), photo=message.photo.name)
            ChatAttachment.objects.create(message=item, file=message.photo.name, kind='image', position=0)
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(len(self.client.get(self.url).json()['messages']), 11)
        self.assertEqual(len(single), len(many))

    def test_attachment_control_is_superuser_only(self):
        from django.template.loader import render_to_string
        for user in (self.owner, self.member, self.staff):
            request = RequestFactory().get('/')
            request.user = user
            html = render_to_string('chat/dialog.html', {'request': request})
            self.assertEqual('id="chatPhotoAttach"' in html, user.is_superuser)
            self.assertIn('id="chatPhotoViewer"', html)
        request.user = self.owner
        self.assertNotIn('id="chatPhotoAttach"', render_to_string('chat/dialog.html', {'request': request, 'is_view_as': True}))

    def test_multiple_attachments_preserve_order_and_cannot_exceed_ten(self):
        rejected = self.client.post(self.url, {'attachments': [self.photo() for _ in range(11)]})
        self.assertEqual(rejected.status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())
        self.assertEqual(self.files(), [])
        response = self.client.post(self.url, {'attachments': [self.photo() for _ in range(10)]})
        self.assertEqual(response.status_code, 201)
        data = response.json()['message']
        self.assertEqual(len(data['attachments']), 10)
        message = ChatMessage.objects.get(pk=data['id'])
        self.assertEqual(list(message.attachments.values_list('position', flat=True)), list(range(10)))
        self.assertEqual(len(self.files()), 10)
        self.assertEqual(self.client.get(self.url).json()['messages'][0]['attachments'], data['attachments'])
        limited = self.client.post(self.url, {'attachments': [self.photo(), self.photo()]})
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(len(self.files()), 10)
        self.allow_send()
        reply = self.client.post(self.url, {'text': 'Reply', 'reply_to': message.pk}, content_type='application/json').json()['message']
        self.assertEqual(reply['reply_to']['attachment_count'], 10)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.delete(reverse('chat:message', args=[message.pk])).status_code, 200)
        self.assertEqual(self.files(), [])
        self.assertEqual(self.client.get(data['attachments'][0]['url']).status_code, 404)

    def test_mixed_webm_and_images_are_private_and_video_is_reencoded_without_audio(self):
        video = SimpleUploadedFile('not-a-video.txt', webm_sample(), content_type='text/plain')
        response = self.client.post(self.url, {'attachments': [video, self.photo()], 'text': ''})
        self.assertEqual(response.status_code, 201)
        data = response.json()['message']
        self.assertEqual([item['kind'] for item in data['attachments']], ['video', 'image'])
        message = ChatMessage.objects.get(pk=data['id'])
        video = message.attachments.first()
        self.assertRegex(video.file.name, r'\A[0-9a-f]{32}\.webm\Z')
        from imageio_ffmpeg import get_ffmpeg_exe
        probe = subprocess.run([get_ffmpeg_exe(), '-hide_banner', '-i', video.file.path],
                               capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        description = probe.stderr.decode('utf8', errors='replace')
        self.assertIn('Video:', description)
        self.assertNotIn('Audio:', description)
        self.assertNotIn('private-fixture', description)
        for user in (self.member, self.staff):
            self.client.force_login(user)
            stored = self.client.get(data['attachments'][0]['url'])
            self.assertEqual(stored.status_code, 200)
            self.assertEqual(stored['Content-Type'], 'video/webm')
            self.assertIn('no-store', stored['Cache-Control'])
            stored.close()
            self.assertEqual(self.client.post(self.url, {'attachments': [self.photo(), self.photo()]}).status_code, 403)
        self.assertEqual(Client().get(data['attachments'][0]['url']).status_code, 401)
        self.assertEqual(Client().post(self.url, {'attachments': [self.photo()]}).status_code, 401)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse('chat:attachment', args=[data['id'] + 1, video.pk])).status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            self.owner.delete()
        self.assertEqual(self.files(), [])

    def test_bad_file_in_batch_rejects_entire_message_and_video_limits(self):
        for content in (b'bad-webm', webm_sample('11'), webm_sample()[:160]):
            with self.subTest(size=len(content)):
                response = self.client.post(self.url, {'attachments': [self.photo(), SimpleUploadedFile('video.webm', content, content_type='video/webm')]})
                self.assertEqual(response.status_code, 400)
                self.assertFalse(ChatMessage.objects.exists())
                self.assertFalse(ChatAttachment.objects.exists())
                self.assertEqual(self.files(), [])
        accepted = self.client.post(self.url, {'attachments': [SimpleUploadedFile('ten.webm', webm_sample('10', False))]})
        self.assertEqual(accepted.status_code, 201)
        message = accepted.json()['message']
        self.assertIsNone(message['photo'])
        edited = self.client.patch(reverse('chat:message', args=[message['id']]), json.dumps({'text': ''}), content_type='application/json')
        self.assertEqual(edited.status_code, 200)

    def test_webm_stickers_keep_transparent_and_partial_alpha_for_vp8_and_vp9(self):
        from imageio_ffmpeg import get_ffmpeg_exe
        for codec in ('libvpx', 'libvpx-vp9'):
            with self.subTest(codec=codec):
                self.allow_send()
                upload = SimpleUploadedFile('sticker.webm', transparent_webm_sample(codec), content_type='video/webm')
                response = self.client.post(self.url, {'attachments': [upload]})
                self.assertEqual(response.status_code, 201, response.content)
                attachment = ChatAttachment.objects.get(message_id=response.json()['message']['id'])
                decoded = subprocess.run([
                    get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
                    '-c:v', 'libvpx-vp9', '-i', attachment.file.path,
                    '-frames:v', '1', '-pix_fmt', 'rgba', '-f', 'rawvideo', '-',
                ], check=True, capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.assertEqual(len(decoded.stdout), 64 * 64 * 4)
                alpha = decoded.stdout[3::4]
                # VPx compression can shift alpha slightly, like color values.
                self.assertLessEqual(alpha[4 * 64 + 4], 5)
                self.assertGreaterEqual(alpha[24 * 64 + 24], 250)
                self.assertLessEqual(abs(alpha[24 * 64 + 40] - 128), 10)

    def test_later_file_or_attachment_insert_failure_cleans_the_whole_batch(self):
        storage = ChatAttachment._meta.get_field('file').storage
        original_save = storage._save
        written = []
        def fail_second(name, content):
            result = original_save(name, content)
            written.append(name)
            if len(written) == 2:
                raise OSError('second write failed')
            return result
        with patch.object(storage, '_save', side_effect=fail_second):
            self.assertEqual(self.client.post(self.url, {'attachments': [self.photo(), self.photo()]}).status_code, 503)
        self.assertEqual(self.files(), [])
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatAttachment.objects.exists())
        self.assertIsNone(ChatReadState.objects.get(user=self.owner).last_sent_at)
        with patch.object(ChatAttachment, 'save', side_effect=DatabaseError('insert failed')):
            self.assertEqual(self.client.post(self.url, {'attachments': [self.photo(), self.photo()]}).status_code, 503)
        self.assertEqual(self.files(), [])
        self.assertFalse(ChatMessage.objects.exists())
        self.assertIsNone(ChatReadState.objects.get(user=self.owner).last_sent_at)


class ChatPhotoMigrationTests(TransactionTestCase):
    def test_existing_photo_is_registered_as_attachment_without_changing_file_or_message(self):
        MigrationExecutor(connection).migrate([('chat', '0003_chatmessage_photo')])
        try:
            old = MigrationExecutor(connection).loader.project_state([('chat', '0003_chatmessage_photo')]).apps
            user = old.get_model('auth', 'User').objects.create(username='legacy-photo')
            message = old.get_model('chat', 'ChatMessage').objects.create(sender_id=user.pk, text='keep', photo='legacy.png')
        finally:
            MigrationExecutor(connection).migrate([('chat', '0004_message_attachments')])
        retained = ChatMessage.objects.get(pk=message.pk)
        self.assertEqual(retained.photo.name, 'legacy.png')
        self.assertEqual(retained.text, 'keep')
        attachment = retained.attachments.get()
        self.assertEqual((attachment.file.name, attachment.kind, attachment.position), ('legacy.png', 'image', 0))

    def test_upgrade_old_messages_keeps_all_data_and_defaults_photo_to_empty(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('chat', '0002_message_actions')])
        try:
            old = executor.loader.project_state([('chat', '0002_message_actions')]).apps
            user = old.get_model('auth', 'User').objects.create(username='chat-photo-migration')
            model = old.get_model('chat', 'ChatMessage')
            message = model.objects.create(sender_id=user.pk, text='Existing')
            model.objects.create(sender_id=user.pk, text='Reply', reply_to=message)
            before = list(model.objects.values())
            state = old.get_model('chat', 'ChatReadState').objects.create(user_id=user.pk, last_read_message_id=message.pk, last_sent_at=timezone.now())
            state_before = old.get_model('chat', 'ChatReadState').objects.values().get(pk=state.pk)
        finally:
            MigrationExecutor(connection).migrate([('chat', '0004_message_attachments')])
        after = list(ChatMessage.objects.values())
        for row in after:
            self.assertEqual(row.pop('photo'), '')
        self.assertEqual(after, before)
        self.assertEqual(ChatReadState.objects.values().get(pk=state.pk), state_before)
