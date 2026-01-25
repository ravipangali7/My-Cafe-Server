from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from core.models import User
import getpass


class Command(BaseCommand):
    help = 'Creates a super admin user with name, phone, password'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating super admin user...\n'))

        # Get name
        name = input('Name: ').strip()
        while not name:
            self.stdout.write(self.style.ERROR('Name cannot be empty.'))
            name = input('Name: ').strip()

        # Get phone
        phone = input('Phone: ').strip()
        while not phone:
            self.stdout.write(self.style.ERROR('Phone cannot be empty.'))
            phone = input('Phone: ').strip()

        # Check if phone already exists
        if User.objects.filter(phone=phone).exists():
            self.stdout.write(self.style.ERROR(f'User with phone {phone} already exists.'))
            return

        # Get password
        password = getpass.getpass('Password: ')
        while not password:
            self.stdout.write(self.style.ERROR('Password cannot be empty.'))
            password = getpass.getpass('Password: ')

        # Get confirm password
        confirm_password = getpass.getpass('Confirm Password: ')
        while not confirm_password:
            self.stdout.write(self.style.ERROR('Confirm password cannot be empty.'))
            confirm_password = getpass.getpass('Confirm Password: ')

        # Validate passwords match
        if password != confirm_password:
            self.stdout.write(self.style.ERROR('Passwords do not match.'))
            return

        try:
            # Create super admin user
            user = User.objects.create_user(
                phone=phone,
                password=password,
                name=name,
                username=phone,  # Set username to phone
                is_staff=True,
                is_superuser=True,
                is_active=True
            )

            self.stdout.write(self.style.SUCCESS(f'\nSuper admin user created successfully!'))
            self.stdout.write(self.style.SUCCESS(f'Name: {user.first_name}'))
            self.stdout.write(self.style.SUCCESS(f'Phone: {user.phone}'))
            self.stdout.write(self.style.SUCCESS(f'Username: {user.username}'))

        except ValidationError as e:
            self.stdout.write(self.style.ERROR(f'Validation error: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating user: {e}'))
