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
        self.assertEqual(set(response.json()['message']), {'id', 'sender', 'text', 'created_at', 'is_own'})
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
