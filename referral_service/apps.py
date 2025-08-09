from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class ReferralServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'referral_service'

    def ready(self):
        """
        Safe initialization without signal registration.
        Only runs in normal operation (not tests/migrations).
        """
        if self._should_initialize():
            self._initialize_components()
            logger.info("ReferralService initialized")

    def _initialize_components(self):
        """Initialize any non-signal components"""
        # Placeholder for future service initializations
        # Example: Cache warming, connection verifications
        pass

    def _should_initialize(self):
        """Environment check"""
        import sys
        if 'test' in sys.argv or 'migrate' in sys.argv:
            logger.debug("Skipping initialization in test/migration mode")
            return False
        return True