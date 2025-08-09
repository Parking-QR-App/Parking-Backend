from django.apps import AppConfig
from django.core.signals import request_started
import logging

logger = logging.getLogger(__name__)

class AuthServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auth_service'

    def ready(self):
        """Initialize the app when Django starts"""
        try:
            # Remove or comment out signal initialization
            # self._initialize_signals()
            logger.debug("AuthService app ready")
        except Exception as e:
            logger.error(f"AuthService app initialization failed: {str(e)}")

    # def _initialize_signals(self, **kwargs):
    #     """Explicitly connect signals after apps are ready"""
    #     try:
    #         from django.db.models.signals import post_save
    #         from .signals.referral_signals import (
    #             handle_user_changes
    #         )
            
    #         # String reference to avoid direct model import
    #         post_save.connect(handle_user_changes, sender='auth_service.User')
            
    #         logger.debug("AuthService signals explicitly connected")
    #     except ImportError as e:
    #         logger.warning(f"Signal connection skipped: {str(e)}")
    #     except Exception as e:
    #         logger.error(f"Signal registration failed: {str(e)}")

    # def _should_initialize(self):
    #     """Environment check for safe initialization"""
    #     import sys
    #     if 'test' in sys.argv or 'migrate' in sys.argv:
    #         logger.debug("Skipping signal registration in test/migration mode")
    #         return False
    #     return True