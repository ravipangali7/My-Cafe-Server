"""
Share Distribution Management Command

Usage:
    python manage.py distribute_shares

This command:
1. Checks the system (super setting) balance
2. If balance > 0, fetches all shareholders (is_shareholder=True)
3. For each shareholder, calculates share amount based on share_percentage
4. Distributes the balance and updates each shareholder's balance
5. Creates dual transactions for each distribution
6. Logs: User ID, Name, Phone, Share Percentage, Amount Distributed
"""

import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import User, SuperSetting
from core.utils.transaction_helpers import process_share_distribution, update_system_balance

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Distribute system balance to shareholders based on their share percentages'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the distribution without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force distribution even if not on distribution day',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']

        self.stdout.write(self.style.NOTICE('=' * 60))
        self.stdout.write(self.style.NOTICE('SHARE DISTRIBUTION COMMAND'))
        self.stdout.write(self.style.NOTICE('=' * 60))

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
            self.stdout.write('')

        # Step 1: Get system settings and balance
        settings = SuperSetting.objects.first()
        if not settings:
            self.stdout.write(self.style.ERROR('SuperSetting not found. Please create settings first.'))
            return

        system_balance = settings.balance
        distribution_day = settings.share_distribution_day

        self.stdout.write(f'System Balance: {system_balance}')
        self.stdout.write(f'Distribution Day: {distribution_day}')
        self.stdout.write('')

        # Check distribution day (unless forced)
        from datetime import date
        today = date.today()
        if not force and today.day != distribution_day:
            self.stdout.write(
                self.style.WARNING(
                    f'Today ({today.day}) is not distribution day ({distribution_day}). '
                    f'Use --force to override.'
                )
            )
            return

        # Step 2: Check if balance > 0
        if system_balance <= 0:
            self.stdout.write(self.style.WARNING('No balance to distribute. System balance is 0 or negative.'))
            return

        # Step 3: Fetch all shareholders
        shareholders = User.objects.filter(is_shareholder=True).order_by('-share_percentage')
        
        if not shareholders.exists():
            self.stdout.write(self.style.WARNING('No shareholders found (is_shareholder=True).'))
            return

        # Calculate total percentage
        total_percentage = sum(s.share_percentage for s in shareholders)
        
        self.stdout.write(f'Found {shareholders.count()} shareholder(s)')
        self.stdout.write(f'Total Share Percentage: {total_percentage}%')
        
        if total_percentage > 100:
            self.stdout.write(self.style.WARNING(f'Warning: Total percentage ({total_percentage}%) exceeds 100%'))
        elif total_percentage < 100:
            self.stdout.write(self.style.NOTICE(f'Note: Total percentage ({total_percentage}%) is less than 100%'))
        
        self.stdout.write('')
        self.stdout.write('-' * 60)
        self.stdout.write('DISTRIBUTION DETAILS')
        self.stdout.write('-' * 60)

        # Step 4: Calculate and distribute shares
        distributions = []
        total_distributed = 0

        for shareholder in shareholders:
            share_amount = int((system_balance * shareholder.share_percentage) / 100)
            
            distributions.append({
                'user_id': shareholder.id,
                'name': shareholder.name,
                'phone': shareholder.phone,
                'share_percentage': shareholder.share_percentage,
                'share_amount': share_amount,
                'current_balance': shareholder.balance,
                'new_balance': shareholder.balance + share_amount
            })
            
            total_distributed += share_amount

            # Log shareholder details
            self.stdout.write(
                f'User ID: {shareholder.id} | '
                f'Name: {shareholder.name} | '
                f'Phone: {shareholder.phone} | '
                f'Share %: {shareholder.share_percentage}% | '
                f'Amount: {share_amount}'
            )

        self.stdout.write('-' * 60)
        self.stdout.write(f'Total to be distributed: {total_distributed}')
        remaining = system_balance - total_distributed
        self.stdout.write(f'Remaining balance (rounding): {remaining}')
        self.stdout.write('')

        if dry_run:
            self.stdout.write(self.style.SUCCESS('DRY RUN COMPLETE - No changes made'))
            return

        # Step 5: Execute the distribution
        self.stdout.write(self.style.NOTICE('Executing distribution...'))
        
        try:
            with transaction.atomic():
                for dist in distributions:
                    shareholder = User.objects.select_for_update().get(id=dist['user_id'])
                    
                    if dist['share_amount'] > 0:
                        # Create dual transaction (system OUT, user IN)
                        txn_system, txn_user = process_share_distribution(
                            shareholder=shareholder,
                            amount=dist['share_amount']
                        )
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'  Distributed {dist["share_amount"]} to {shareholder.name} '
                                f'(Transaction #{txn_user.id})'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'  Skipped {shareholder.name} (0 amount due to low percentage)'
                            )
                        )

                # Update system balance
                settings.balance = remaining
                settings.save()
                
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS(f'System balance updated: {remaining}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during distribution: {str(e)}'))
            logger.exception('Share distribution failed')
            return

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('SHARE DISTRIBUTION COMPLETED SUCCESSFULLY'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        
        # Summary
        self.stdout.write('')
        self.stdout.write('SUMMARY:')
        self.stdout.write(f'  - Previous System Balance: {system_balance}')
        self.stdout.write(f'  - Total Distributed: {total_distributed}')
        self.stdout.write(f'  - New System Balance: {remaining}')
        self.stdout.write(f'  - Shareholders Processed: {len(distributions)}')
