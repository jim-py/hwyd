from faker import Faker
import random
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'my_site.settings')
django.setup()

from budget.models import AccountType, Currency, Category, Account, Goal, Transaction
from django.contrib.auth import get_user_model

fake = Faker('ru_RU')
User = get_user_model()


def populate_account_types(n):
    for _ in range(n):
        name = fake.word()
        AccountType.objects.create(name=name)


def populate_currencies(n):
    for _ in range(n):
        name = fake.currency_name()
        exchange_rate = fake.random_number(digits=2) + fake.random_number(digits=2) / 100
        Currency.objects.create(name=name, exchange_rate=exchange_rate)


def populate_categories(n):
    user = User.objects.get(id=76)
    TYPE_CHOICES = ['I', 'E', 'T']

    for _ in range(n):
        name = fake.word()
        type_choice = random.choice(TYPE_CHOICES)
        color = fake.hex_color()
        icon = fake.file_name(category='image')  # или другой подход для получения названия иконки
        Category.objects.create(user=user, name=name, type=type_choice, color=color, icon=icon)


def populate_accounts(n):
    user = User.objects.get(id=76)  # Замените на вашего пользователя
    for _ in range(n):
        account_type = random.choice(AccountType.objects.all())
        currency = random.choice(Currency.objects.all())
        name = fake.company()
        balance = fake.random_number(digits=5)
        initial_balance = fake.random_number(digits=5)
        opening_date = fake.date_this_decade()
        closing_date = None  # или fake.date() для установки даты закрытия
        interest_rate = None  # или fake.random_number(digits=3)/100 для процентной ставки
        credit_limit = None  # или fake.random_number(digits=5) для кредитного лимита
        Account.objects.create(
            user=user,
            account_type=account_type,
            currency=currency,
            name=name,
            balance=balance,
            initial_balance=initial_balance,
            opening_date=opening_date,
            closing_date=closing_date,
            interest_rate=interest_rate,
            credit_limit=credit_limit,
        )


def populate_goals(n):
    for _ in range(n):
        account = random.choice(Account.objects.all())
        name = fake.sentence(nb_words=3)
        amount = fake.random_number(digits=5)
        Goal.objects.create(account=account, name=name, amount=amount)


def populate_transactions(n):
    user = User.objects.get(id=76)  # Замените на вашего пользователя
    for _ in range(n):
        category = random.choice(Category.objects.all())
        account = random.choice(Account.objects.all())
        date = fake.date_this_month()
        amount = fake.random_number(digits=5)
        description = fake.text(max_nb_chars=200)

        Transaction.objects.create(
            user=user,
            category=category,
            account=account,
            date=date,
            amount=amount,
            description=description,
            regular=fake.boolean(),
            permanent=fake.boolean(),
        )


# Функции вызываются здесь, или вы можете вызвать их из другого места, например, из команды Django
populate_account_types(10)
populate_currencies(10)
populate_categories(30)
populate_accounts(50)
populate_goals(20)
populate_transactions(100)
