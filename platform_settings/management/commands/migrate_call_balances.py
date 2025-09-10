# platform_settings/management/commands/migrate_call_balances.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging

from auth_service.models import User
from platform_settings.services import CallBalanceService
from shared.utils.api_exceptions import ServiceUnavailableException, DataValidationException

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Migrate call balances from legacy system to platform settings'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of users to process in each batch'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate migration without saving changes'
        )
    
    def handle(self, *args, **options):
        batch_size = options['batch_size']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.MIGRATE_HEADING('Starting call balance migration...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be saved')
            )
        
        migrated_count = 0
        error_count = 0
        skipped_count = 0
        
        # Get all users
        users = User.objects.all()
        total_users = users.count()
        
        self.stdout.write(f"Processing {total_users} users...")
        
        for i, user in enumerate(users, 1):
            try:
                # Skip users with no legacy balance
                if not hasattr(user, '_call_balance') or user._call_balance == Decimal('0.00'):
                    skipped_count += 1
                    continue
                
                if dry_run:
                    # Just simulate the migration
                    balance = CallBalanceService.get_user_balance(user)
                    legacy_balance = user._call_balance
                    
                    self.stdout.write(
                        f"Would migrate user {user.user_id}: "
                        f"Legacy={legacy_balance} → New={balance.total_balance}"
                    )
                    migrated_count += 1
                else:
                    with transaction.atomic():
                        # Create or get user balance
                        balance = CallBalanceService.get_user_balance(user)
                        
                        # Migrate legacy balance to base balance
                        legacy_balance = Decimal(str(user._call_balance))
                        balance.base_balance = legacy_balance
                        balance.save()
                        
                        migrated_count += 1
                
                # Progress update
                if i % batch_size == 0:
                    self.stdout.write(
                        f"Processed {i}/{total_users} users "
                        f"({migrated_count} migrated, {error_count} errors, {skipped_count} skipped)"
                    )
                        
            except DataValidationException as e:
                error_count += 1
                logger.error(f"Data validation failed for user {user.id}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Validation error for user {user.id}: {str(e)}")
                )
                
            except ServiceUnavailableException as e:
                error_count += 1
                logger.error(f"Service unavailable for user {user.id}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Service error for user {user.id}: {str(e)}")
                )
                
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to migrate user {user.id}: {str(e)}")
                self.stdout.write(
                    self.style.ERROR(f"Unexpected error for user {user.id}: {str(e)}")
                )
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(
            self.style.MIGRATE_LABEL('MIGRATION SUMMARY:')
        )
        self.stdout.write(f"Total users processed: {total_users}")
        self.stdout.write(f"Successfully migrated: {migrated_count}")
        self.stdout.write(f"Skipped (no balance): {skipped_count}")
        self.stdout.write(f"Errors: {error_count}")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETED - No changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('Migration completed successfully!')
            )
            
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Warning: {error_count} errors occurred during migration')
            )



# 1. Migrate Call Balances Command
# Basic migration:

# bash
# python manage.py migrate_call_balances
# Dry run (test without making changes):

# bash
# python manage.py migrate_call_balances --dry-run
# Custom batch size:

# bash
# python manage.py migrate_call_balances --batch-size 50
# Dry run with custom batch size:

# bash
# python manage.py migrate_call_balances --dry-run --batch-size 50


# Migration Command Output:
# text
# Starting call balance migration...
# Processing 1500 users...
# Processed 100/1500 users (85 migrated, 2 errors, 13 skipped)
# Processed 200/1500 users (170 migrated, 3 errors, 27 skipped)
# ...

# ==================================================
# MIGRATION SUMMARY:
# Total users processed: 1500
# Successfully migrated: 1275
# Skipped (no balance): 200
# Errors: 25

# Migration completed successfully!
# Warning: 25 errors occurred during migration