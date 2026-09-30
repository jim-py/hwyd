self.addEventListener('push', function(event) {
  if (!event.data) {
    console.error('Push event but no data');
    return;
  }

  const data = event.data.json();

  const title = data.title || 'Уведомление';
  const options = {
    body: data.body || '',
    icon: data.icon || '/static/site/images/logo.png',
    badge: data.badge || '/static/site/images/logo.png',
    // Можно добавить другие опции, например actions, vibrate, tag и т.д.
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});
