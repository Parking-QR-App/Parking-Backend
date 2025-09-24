from django.core.management.base import BaseCommand
from django.db import ProgrammingError, OperationalError, transaction
from referral_service.models import ReferralSettings
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Initialize default referral settings'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Initializing Referral Settings...'))

        defaults = {
            'default_reward_calls': '5.00',
            'referral_code_length': '8',
        }

        created_count = 0
        skipped_count = 0
        error_count = 0

        for key, value in defaults.items():
            try:
                # Wrap in a transaction to ensure atomicity
                with transaction.atomic():
                    # Check if the table exists and the setting already exists
                    existing = ReferralSettings.objects.filter(key=key).first()
                    if existing:
                        skipped_count += 1
                        self.stdout.write(self.style.NOTICE(f"SKIPPED: {key} (already exists)"))
                    else:
                        # Create the new setting
                        ReferralSettings.objects.create(
                            key=key,
                            value=value,
                            description=f"Default {key}"
                        )
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f"CREATED: {key}"))
            except (ProgrammingError, OperationalError) as e:
                error_count += 1
                logger.error(f"Database error for setting {key}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"DB ERROR: {key} - {str(e)}"))
            except Exception as e:
                error_count += 1
                logger.error(f"Unexpected error for setting {key}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"ERROR: {key} - {str(e)}"))

        # Summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.MIGRATE_LABEL('INITIALIZATION SUMMARY:'))
        self.stdout.write(f"Total settings processed: {len(defaults)}")
        self.stdout.write(f"New settings created: {created_count}")
        self.stdout.write(f"Existing settings skipped: {skipped_count}")
        self.stdout.write(f"Errors: {error_count}")

        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Warning: {error_count} errors occurred during initialization"))
        else:
            self.stdout.write(self.style.SUCCESS("Referral settings initialization completed successfully!"))

        # Show the initialized settings if any were created
        if created_count > 0:
            self.stdout.write("\n" + self.style.MIGRATE_LABEL('CURRENT SETTINGS:'))
            try:
                for setting in ReferralSettings.objects.all().order_by('key'):
                    self.stdout.write(f"  {setting.key}: {setting.value}")
            except (ProgrammingError, OperationalError) as e:
                self.stdout.write(self.style.ERROR(f"Failed to fetch settings: {str(e)}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Unexpected error fetching settings: {str(e)}"))
