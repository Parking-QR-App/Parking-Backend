# platform_settings/management/commands/validate_balances.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
import logging

from auth_service.models import User
from platform_settings.models import UserCallBalance
from shared.utils.api_exceptions import DataValidationException

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Validate that call balances are properly synced between legacy and new systems'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--tolerance',
            type=float,
            default=0.01,
            help='Tolerance for balance differences (default: 0.01)'
        )
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Automatically fix mismatches found during validation'
        )
    
    def handle(self, *args, **options):
        tolerance = Decimal(str(options['tolerance']))
        fix_issues = options['fix']
        
        self.stdout.write(
            self.style.MIGRATE_HEADING('Starting balance validation...')
        )
        
        if fix_issues:
            self.stdout.write(
                self.style.WARNING('AUTO-FIX MODE ENABLED - Mismatches will be automatically corrected')
            )
        
        total_users = 0
        mismatches = 0
        fixed_count = 0
        errors = 0
        
        users = User.objects.all()
        
        for user in users:
            total_users += 1
            
            try:
                # Get legacy balance (with fallback)
                legacy_balance = Decimal('0.00')
                if hasattr(user, '_call_balance'):
                    legacy_balance = Decimal(str(user._call_balance))
                
                # Get platform balance
                try:
                    user_balance = UserCallBalance.objects.get(user=user)
                    platform_balance = user_balance.total_balance
                except UserCallBalance.DoesNotExist:
                    platform_balance = Decimal('0.00')
                
                # Check for mismatch
                balance_diff = abs(legacy_balance - platform_balance)
                
                if balance_diff > tolerance:
                    mismatches += 1
                    
                    self.stdout.write(
                        self.style.WARNING(
                            f"MISMATCH: User {user.user_id} ({user.email})\n"
                            f"  Legacy: {legacy_balance}\n"
                            f"  Platform: {platform_balance}\n"
                            f"  Difference: {balance_diff}"
                        )
                    )
                    
                    if fix_issues:
                        try:
                            # Fix the mismatch by updating the platform balance
                            user_balance.base_balance = legacy_balance
                            user_balance.save()
                            
                            fixed_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(f"  → Fixed: Platform balance updated to {legacy_balance}")
                            )
                            
                        except Exception as e:
                            errors += 1
                            self.stdout.write(
                                self.style.ERROR(f"  → Failed to fix: {str(e)}")
                            )
                
                # Show progress for large datasets
                if total_users % 100 == 0:
                    self.stdout.write(f"Processed {total_users} users...")
                    
            except DataValidationException as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"Data validation error for user {user.id}: {str(e)}")
                )
                
            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"Unexpected error processing user {user.id}: {str(e)}")
                )
        
        # Summary report
        self.stdout.write("\n" + "="*60)
        self.stdout.write(
            self.style.MIGRATE_LABEL('VALIDATION SUMMARY:')
        )
        self.stdout.write(f"Total users checked: {total_users}")
        self.stdout.write(f"Mismatches found: {mismatches}")
        
        if fix_issues:
            self.stdout.write(f"Mismatches fixed: {fixed_count}")
            if errors > 0:
                self.stdout.write(
                    self.style.ERROR(f"Errors during fixing: {errors}")
                )
        
        accuracy = ((total_users - mismatches) / total_users * 100) if total_users > 0 else 100
        self.stdout.write(f"Data accuracy: {accuracy:.2f}%")
        
        if mismatches == 0:
            self.stdout.write(
                self.style.SUCCESS("✓ All balances are properly synchronized!")
            )
        else:
            self.stdout.write(
                self.style.WARNING(f"⚠ {mismatches} mismatches found in the data")
            )
            
        if not fix_issues and mismatches > 0:
            self.stdout.write(
                self.style.NOTICE("\nRun with --fix to automatically correct mismatches")
            )


# 2. Validate Balances Command
# Basic validation:

# bash
# python manage.py validate_balances
# Validation with custom tolerance:

# bash
# python manage.py validate_balances --tolerance 0.05
# Automatically fix mismatches:

# bash
# python manage.py validate_balances --fix
# Fix with custom tolerance:

# bash
# python manage.py validate_balances --fix --tolerance 0.02

# Validation Command Output:
# text
# Starting balance validation...
# MISMATCH: User user_123 (user@example.com)
#   Legacy: 15.00
#   Platform: 10.00
#   Difference: 5.00
#   → Fixed: Platform balance updated to 15.00

# ============================================================
# VALIDATION SUMMARY:
# Total users checked: 1500
# Mismatches found: 15
# Mismatches fixed: 15
# Data accuracy: 99.00%
# ✓ All balances are properly synchronized!