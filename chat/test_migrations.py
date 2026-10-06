from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class ChatMigrationTests(TransactionTestCase):
    def test_adopt_existing_tables_then_add_reply_without_data_loss(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('chat', '0001_initial')])
        old = executor.loader.project_state([('chat', '0001_initial')]).apps
        user = old.get_model('auth', 'User').objects.create(username='migration-user')
        message = old.get_model('chat', 'ChatMessage').objects.create(sender_id=user.pk, text='keep me')
        old.get_model('chat', 'ChatReadState').objects.create(user_id=user.pk, last_read_message_id=message.pk)
        try:
            # Legacy syncdb installations may have tables but no migration record.
            MigrationRecorder(connection).record_unapplied('chat', '0001_initial')
            MigrationExecutor(connection).migrate([('chat', '0001_initial')], fake_initial=True)
            self.assertIn(('chat', '0001_initial'), MigrationRecorder(connection).applied_migrations())
        finally:
            MigrationExecutor(connection).migrate([('chat', '0004_message_attachments')])
        from .models import ChatMessage, ChatReadState
        retained = ChatMessage.objects.get(pk=message.pk)
        self.assertEqual(retained.text, 'keep me')
        self.assertIsNone(retained.reply_to_id)
        self.assertIsNone(retained.deleted_at)
        self.assertFalse(retained.photo)
        self.assertEqual(ChatReadState.objects.get(user_id=user.pk).last_read_message_id, message.pk)
        reply = ChatMessage.objects.create(sender_id=user.pk, text='reply', reply_to=retained)
        self.assertEqual(ChatMessage.objects.get(pk=reply.pk).reply_to_id, message.pk)
