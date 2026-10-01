import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.middleware.csrf import get_token
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ChatMessage, ChatReadState, MESSAGE_MAX_LENGTH
from .views import PAGE_SIZE


@override_settings(MIDDLEWARE=[
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
])
class ChatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user(username='alice')
        cls.bob = get_user_model().objects.create_user(username='bob')

    def setUp(self):
        self.client.force_login(self.alice)
        self.messages_url = reverse('chat:messages')
        self.status_url = reverse('chat:status')
        self.read_url = reverse('chat:read')

    def post(self, url, data, client=None):
        return (client or self.client).post(url, json.dumps(data), content_type='application/json')

    def test_anonymous_cannot_read_send_check_status_or_mark_read(self):
        client = Client()
        self.assertEqual(client.get(self.messages_url).status_code, 401)
        self.assertEqual(client.get(self.status_url).status_code, 401)
        self.assertEqual(self.post(self.messages_url, {'text': 'Hello'}, client).status_code, 401)
        self.assertEqual(self.post(self.read_url, {'last_read_message_id': 0}, client).status_code, 401)
        self.assertFalse(ChatMessage.objects.exists())

    def test_sender_comes_from_session_and_json_is_minimal(self):
        response = self.post(self.messages_url, {'text': ' Привет 👋 ', 'sender_id': self.bob.pk})
        self.assertEqual(response.status_code, 201)
        message = ChatMessage.objects.get()
        self.assertEqual(message.sender, self.alice)
        self.assertEqual(message.text, 'Привет 👋')
        self.assertEqual(set(response.json()['message']), {
            'id', 'sender', 'sender_id', 'text', 'created_at', 'is_own', 'edited_at', 'is_deleted', 'reply_to'})
        self.client.force_login(self.bob)
        data = self.client.get(self.messages_url).json()['messages'][0]
        self.assertEqual(data['sender'], 'alice')
        self.assertFalse(data['is_own'])

    def test_empty_wrong_type_and_long_messages_rejected(self):
        for value in ['', ' \n\t ', None, 123, [], {}, 'x' * (MESSAGE_MAX_LENGTH + 1), '\ud800']:
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(self.post(self.messages_url, {'text': value}).status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatReadState.objects.exists())

    def test_max_length_message_accepted(self):
        self.assertEqual(self.post(self.messages_url, {'text': 'x' * MESSAGE_MAX_LENGTH}).status_code, 201)

    def test_malformed_and_oversized_bodies_rejected(self):
        for body in ['{', 'null', '[]', '"text"', json.dumps({'text': 'x' * 13000})]:
            self.assertEqual(self.client.post(self.messages_url, body, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(self.messages_url, {'text': 'hello'}).status_code, 400)
        self.assertFalse(ChatMessage.objects.exists())

    def test_xss_and_emoji_are_literal_data(self):
        text = '<script>alert(1)</script> 😀\n<img src=x onerror=alert(2)>'
        self.assertEqual(self.post(self.messages_url, {'text': text}).status_code, 201)
        self.assertEqual(ChatMessage.objects.get().text, text)
        self.assertEqual(self.client.get(self.messages_url).json()['messages'][0]['text'], text)

    def test_cooldown_persists_across_clients_and_is_per_user(self):
        self.assertEqual(self.post(self.messages_url, {'text': 'first'}).status_code, 201)
        other_client = Client()
        other_client.force_login(self.alice)
        limited = self.post(self.messages_url, {'text': 'second'}, other_client)
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited['Retry-After'], '2')
        self.client.force_login(self.bob)
        self.assertEqual(self.post(self.messages_url, {'text': 'bob'}).status_code, 201)
        ChatReadState.objects.filter(user=self.alice).update(last_sent_at=timezone.now() - timedelta(seconds=3))
        self.assertEqual(self.post(self.messages_url, {'text': 'later'}, other_client).status_code, 201)
        self.assertEqual(ChatMessage.objects.count(), 3)

    def test_unread_other_user_read_ack_and_own_messages(self):
        own = ChatMessage.objects.create(sender=self.alice, text='own')
        self.assertFalse(self.client.get(self.status_url).json()['has_unread'])
        other = ChatMessage.objects.create(sender=self.bob, text='other')
        self.assertTrue(self.client.get(self.status_url).json()['has_unread'])
        # A GET does not mark messages read or create state.
        self.client.get(self.messages_url)
        self.assertFalse(ChatReadState.objects.exists())
        self.assertTrue(self.client.get(self.status_url).json()['has_unread'])
        self.assertEqual(self.post(self.read_url, {'last_read_message_id': other.pk, 'user_id': self.bob.pk}).status_code, 200)
        self.assertFalse(self.client.get(self.status_url).json()['has_unread'])
        self.assertFalse(ChatReadState.objects.filter(user=self.bob).exists())
        self.post(self.read_url, {'last_read_message_id': own.pk})
        self.assertEqual(ChatReadState.objects.get(user=self.alice).last_read_message_id, other.pk)
        ChatMessage.objects.create(sender=self.bob, text='new')
        self.assertTrue(self.client.get(self.status_url).json()['has_unread'])

    def test_initial_tail_and_incremental_bounded_pages(self):
        items = [ChatMessage.objects.create(sender=self.bob, text=str(i)) for i in range(PAGE_SIZE + 5)]
        initial = self.client.get(self.messages_url).json()
        self.assertEqual([m['id'] for m in initial['messages']], [m.pk for m in items[-PAGE_SIZE:]])
        page = self.client.get(self.messages_url, {'after_id': 0}).json()
        self.assertTrue(page['has_more'])
        self.assertEqual([m['id'] for m in page['messages']], [m.pk for m in items[:PAGE_SIZE]])
        next_page = self.client.get(self.messages_url, {'after_id': page['messages'][-1]['id']}).json()
        self.assertFalse(next_page['has_more'])
        self.assertEqual(len(next_page['messages']), 5)

    def test_invalid_cursors_and_methods(self):
        for cursor in ['-1', 'abc', '1.5', '', '9' * 30]:
            self.assertEqual(self.client.get(self.messages_url, {'after_id': cursor}).status_code, 400)
        for cursor in [-1, True, '1', None, 2 ** 63, 99999]:
            self.assertEqual(self.post(self.read_url, {'last_read_message_id': cursor}).status_code, 400)
        self.assertEqual(self.client.get(self.read_url).status_code, 405)
        self.assertEqual(self.post(self.status_url, {}).status_code, 405)
        self.assertEqual(self.client.delete(self.messages_url).status_code, 405)

    def test_csrf_required_for_both_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.alice)
        for url, payload in [(self.messages_url, {'text': 'Hello'}), (self.read_url, {'last_read_message_id': 0})]:
            self.assertEqual(self.post(url, payload, client).status_code, 403)
        request = RequestFactory().get('/')
        token = get_token(request)
        client.cookies['csrftoken'] = request.META['CSRF_COOKIE']
        response = client.post(self.messages_url, json.dumps({'text': 'With CSRF'}),
                               content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201)

    def test_responses_cannot_be_cached(self):
        self.assertIn('no-store', self.client.get(self.messages_url)['Cache-Control'])
        self.assertIn('no-store', self.client.get(self.status_url)['Cache-Control'])

    def detail_url(self, message):
        return reverse('chat:message', args=[message.pk])

    def patch(self, message, text, client=None):
        return (client or self.client).patch(self.detail_url(message), json.dumps({'text': text}),
                                            content_type='application/json')

    def test_own_edit_persists_and_uses_create_validation(self):
        message = ChatMessage.objects.create(sender=self.alice, text='before')
        response = self.patch(message, '  Изменено <img src=x onerror=alert(1)> 😀  ')
        self.assertEqual(response.status_code, 200)
        message.refresh_from_db()
        self.assertEqual(message.text, 'Изменено <img src=x onerror=alert(1)> 😀')
        self.assertIsNotNone(message.edited_at)
        self.assertEqual(self.client.get(self.messages_url).json()['messages'][0]['text'], message.text)
        for text in ['', ' \n ', 123, None, '\ud800', 'x' * (MESSAGE_MAX_LENGTH + 1)]:
            self.assertEqual(self.patch(message, text).status_code, 400)
        message.refresh_from_db()
        self.assertEqual(message.text, response.json()['message']['text'])

    def test_other_user_even_staff_cannot_edit_or_delete(self):
        message = ChatMessage.objects.create(sender=self.bob, text='protected')
        self.alice.is_staff = True
        self.alice.save(update_fields=['is_staff'])
        self.assertEqual(self.patch(message, 'forged').status_code, 403)
        self.assertEqual(self.client.delete(self.detail_url(message)).status_code, 403)
        message.refresh_from_db()
        self.assertEqual(message.text, 'protected')
        self.assertIsNone(message.deleted_at)

    def test_own_delete_erases_text_and_does_not_resurrect(self):
        message = ChatMessage.objects.create(sender=self.alice, text='secret old text')
        response = self.client.delete(self.detail_url(message))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['message']['is_deleted'])
        message.refresh_from_db()
        self.assertEqual(message.text, '')
        self.assertIsNotNone(message.deleted_at)
        self.assertEqual(self.client.get(self.messages_url).json()['messages'], [])
        self.assertEqual(self.patch(message, 'resurrect').status_code, 404)
        self.assertEqual(self.client.delete(self.detail_url(message)).status_code, 404)

    def test_reply_persists_and_deleted_target_is_safe(self):
        self.bob.first_name = ' Борис '
        self.bob.save(update_fields=['first_name'])
        target = ChatMessage.objects.create(sender=self.bob, text='x' * 500)
        response = self.post(self.messages_url, {'text': 'Ответ', 'reply_to': target.pk})
        self.assertEqual(response.status_code, 201)
        reply = ChatMessage.objects.get(pk=response.json()['message']['id'])
        self.assertEqual(reply.reply_to_id, target.pk)
        data = self.client.get(self.messages_url).json()['messages'][-1]
        self.assertEqual(data['reply_to']['sender'], 'Борис')
        self.assertEqual(data['reply_to']['text'], 'x' * 160)
        self.assertEqual(data['reply_to']['preview_text'], 'x' * 224)
        self.client.force_login(self.bob)
        self.assertEqual(self.client.delete(self.detail_url(target)).status_code, 200)
        reply.refresh_from_db()
        self.assertEqual(reply.reply_to_id, target.pk)
        data = self.client.get(self.messages_url).json()['messages'][0]
        self.assertTrue(data['reply_to']['is_deleted'])
        self.assertEqual(data['reply_to']['text'], '')
        self.assertEqual(data['reply_to']['preview_text'], '')
        self.assertEqual(self.post(self.messages_url, {'text': 'late', 'reply_to': target.pk}).status_code, 404)
        # Actual row removal, e.g. account removal, also safely nulls the relation.
        target.delete()
        reply.refresh_from_db()
        self.assertIsNone(reply.reply_to_id)

    def test_reply_preview_has_bounded_lookahead_for_composed_emoji(self):
        for emoji in ['👨‍👩‍👧‍👦', '🏃🏽‍♀️', '🇳🇱', '1️⃣', '👍🏿']:
            with self.subTest(emoji=emoji):
                target = ChatMessage.objects.create(sender=self.bob, text='a' * 159 + emoji + 'x' * 500)
                reply = ChatMessage.objects.create(sender=self.alice, text='Ответ', reply_to=target)
                from .views import serialize
                preview = serialize(reply, self.alice)['reply_to']
                self.assertEqual(len(preview['text']), 160)
                self.assertEqual(len(preview['preview_text']), 224)
                self.assertIn(emoji, preview['preview_text'])

    def test_reply_id_validation_and_missing_target(self):
        for value in [True, False, 0, -1, '1', [], {}, 2 ** 63]:
            self.assertEqual(self.post(self.messages_url, {'text': 'reply', 'reply_to': value}).status_code, 400)
        self.assertEqual(self.post(self.messages_url, {'text': 'reply', 'reply_to': 99999}).status_code, 404)
        self.assertFalse(ChatMessage.objects.exists())

    def test_name_fallback_and_author_identity(self):
        self.alice.first_name = '<b>Анна</b>'
        self.alice.save(update_fields=['first_name'])
        first = ChatMessage.objects.create(sender=self.alice, text='one')
        ChatMessage.objects.create(sender=self.bob, text='two')
        data = self.client.get(self.messages_url).json()['messages']
        self.assertEqual(data[0]['sender'], '<b>Анна</b>')
        self.assertEqual(data[0]['sender_id'], first.sender_id)
        self.assertEqual(data[1]['sender'], 'bob')
        self.alice.first_name = ' \t '
        self.alice.save(update_fields=['first_name'])
        self.assertEqual(self.client.get(self.messages_url).json()['messages'][0]['sender'], 'alice')

    def test_bounded_refresh_returns_edits_deletions_and_missing_ids(self):
        own = ChatMessage.objects.create(sender=self.alice, text='old')
        other = ChatMessage.objects.create(sender=self.bob, text='remove')
        self.patch(own, 'new')
        self.client.force_login(self.bob)
        self.client.delete(self.detail_url(other))
        data = self.client.get(self.messages_url, {'after_id': other.pk,
            'refresh_ids': f'{own.pk},{other.pk},99999'}).json()
        self.assertEqual(data['messages'], [])
        self.assertEqual(data['updated_messages'][0]['text'], 'new')
        self.assertTrue(data['updated_messages'][1]['is_deleted'])
        self.assertEqual(data['missing_ids'], [99999])
        for value in ['', '1,abc', '0', '-1', 'true', str(2 ** 63), ','.join(['1'] * 51)]:
            self.assertEqual(self.client.get(self.messages_url, {'refresh_ids': value}).status_code, 400)
        self.client.force_login(self.alice)
        self.assertFalse(self.client.get(self.status_url).json()['has_unread'])
        self.assertEqual(self.post(self.read_url, {'last_read_message_id': other.pk}).status_code, 200)

    def test_detail_auth_methods_and_csrf(self):
        message = ChatMessage.objects.create(sender=self.alice, text='unchanged')
        self.assertEqual(self.client.delete(reverse('chat:message', args=[2 ** 63])).status_code, 400)
        self.assertEqual(self.client.delete(reverse('chat:message', args=[0])).status_code, 400)
        anonymous = Client()
        self.assertEqual(self.patch(message, 'bad', anonymous).status_code, 401)
        self.assertEqual(anonymous.delete(self.detail_url(message)).status_code, 401)
        self.assertEqual(self.client.get(self.detail_url(message)).status_code, 405)
        self.assertEqual(self.client.post(self.detail_url(message)).status_code, 405)
        secured = Client(enforce_csrf_checks=True)
        secured.force_login(self.alice)
        self.assertEqual(self.patch(message, 'bad', secured).status_code, 403)
        self.assertEqual(secured.delete(self.detail_url(message)).status_code, 403)
        request = RequestFactory().get('/')
        token = get_token(request)
        secured.cookies['csrftoken'] = request.META['CSRF_COOKIE']
        response = secured.patch(self.detail_url(message), json.dumps({'text': 'With CSRF'}),
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        response = secured.delete(self.detail_url(message), HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
