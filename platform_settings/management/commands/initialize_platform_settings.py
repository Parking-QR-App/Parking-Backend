# platform_settings/management/commands/initialize_platform_settings.py
from django.core.management.base import BaseCommand
import logging

from platform_settings.models import PlatformSetting
from shared.utils.api_exceptions import ServiceUnavailableException, DataValidationException
from platform_settings.services import DefaultSettings
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Initialize default platform settings for call management and referral system'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-initialization even if settings already exist'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without making changes'
        )
    
    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']
        
        self.stdout.write(
            self.style.MIGRATE_HEADING('Initializing Platform Settings...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        try:
            for setting_data in DefaultSettings.DEFAULT_SETTINGS:
                try:
                    key = setting_data['key']
                    
                    # Check if setting already exists
                    existing_setting = PlatformSetting.objects.filter(key=key).first()
                    
                    if existing_setting:
                        if force:
                            # Update existing setting in force mode
                            if not dry_run:
                                for field, value in setting_data.items():
                                    if hasattr(existing_setting, field):
                                        setattr(existing_setting, field, value)
                                existing_setting.save()
                                updated_count += 1
                            
                            self.stdout.write(
                                self.style.WARNING(f"UPDATED: {key} (forced update)")
                            )
                        else:
                            # Skip existing setting
                            skipped_count += 1
                            self.stdout.write(
                                self.style.NOTICE(f"SKIPPED: {key} (already exists)")
                            )
                    else:
                        # Create new setting
                        if not dry_run:
                            PlatformSetting.objects.create(**setting_data)
                            created_count += 1
                        
                        self.stdout.write(
                            self.style.SUCCESS(f"CREATED: {key}")
                        )
                        
                except DataValidationException as e:
                    error_count += 1
                    logger.error(f"Data validation failed for setting {key}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f"VALIDATION ERROR: {key} - {str(e)}")
                    )
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Failed to process setting {key}: {str(e)}")
                    self.stdout.write(
                        self.style.ERROR(f"ERROR: {key} - {str(e)}")
                    )
        
        except Exception as e:
            logger.error(f"Failed to initialize platform settings: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to initialize platform settings",
                context={'error': str(e)}
            )
        
        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(
            self.style.MIGRATE_LABEL('INITIALIZATION SUMMARY:')
        )
        self.stdout.write(f"Total settings processed: {len(DefaultSettings.DEFAULT_SETTINGS)}")
        self.stdout.write(f"New settings created: {created_count}")
        
        if force:
            self.stdout.write(f"Existing settings updated: {updated_count}")
        else:
            self.stdout.write(f"Existing settings skipped: {skipped_count}")
        
        self.stdout.write(f"Errors: {error_count}")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETED - No changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('Platform settings initialization completed successfully!')
            )
            
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Warning: {error_count} errors occurred during initialization')
            )
        
        # Show the initialized settings
        if not dry_run and (created_count > 0 or (force and updated_count > 0)):
            self.stdout.write("\n" + self.style.MIGRATE_LABEL('CURRENT SETTINGS:'))
            for setting in PlatformSetting.objects.all().order_by('category', 'key'):
                value_display = self._format_setting_value(setting)
                self.stdout.write(
                    f"  {setting.key}: {value_display} ({setting.category})"
                )
    
    def _format_setting_value(self, setting):
        """Format setting value for display"""
        if setting.setting_type == 'boolean':
            return 'Yes' if setting.boolean_value else 'No'
        elif setting.setting_type == 'decimal':
            return f"{setting.decimal_value}"
        elif setting.setting_type == 'integer':
            return f"{setting.integer_value}"
        else:
            return f"'{setting.string_value}'"
        

# Basic initialization:
# bash
# python manage.py initialize_platform_settings
# Dry run (see what would be created):
# bash
# python manage.py initialize_platform_settings --dry-run
# Force re-initialization (update existing settings):
# bash
# python manage.py initialize_platform_settings --force
# Dry run with force mode:
# bash
# python manage.py initialize_platform_settings --force --dry-run
# 📋 Expected Output Examples
# Normal Initialization:
# text
# Initializing Platform Settings...
# CREATED: initial_call_balance
# CREATED: cron_reset_enabled
# CREATED: cron_reset_frequency
# CREATED: cron_reset_amount
# CREATED: referral_reward_calls

# ==================================================
# INITIALIZATION SUMMARY:
# Total settings processed: 5
# New settings created: 5
# Existing settings skipped: 0
# Errors: 0

# Platform settings initialization completed successfully!

# CURRENT SETTINGS:
#   cron_reset_amount: 5.00 (call_management)
#   cron_reset_enabled: Yes (call_management)
#   cron_reset_frequency: 7 (call_management)
#   initial_call_balance: 10.00 (call_management)
#   referral_reward_calls: 5.00 (referral_system)
# Force Re-initialization:
# text
# Initializing Platform Settings...
# UPDATED: initial_call_balance (forced update)
# UPDATED: cron_reset_enabled (forced update)
# UPDATED: cron_reset_frequency (forced update)
# UPDATED: cron_reset_amount (forced update)
# UPDATED: referral_reward_calls (forced update)

# ==================================================
# INITIALIZATION SUMMARY:
# Total settings processed: 5
# New settings created: 0
# Existing settings updated: 5
# Errors: 0

# Platform settings initialization completed successfully!