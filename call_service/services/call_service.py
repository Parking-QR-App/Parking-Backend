from django.utils import timezone
from utils.cache import set_call_cache, CACHE_TTL
from django.db import transaction, DatabaseError, IntegrityError
from django.db.models import Q, Count, Sum, Avg
from decimal import Decimal
from django.apps import apps
import logging

from shared.utils.api_exceptions import (
    ValidationException, 
    InsufficientBalanceException,
    NotFoundException,  # Fixed - use NotFoundException instead of ResourceNotFoundException
    ServiceUnavailableException,
    AuthenticationException,
    ConflictException  # Added missing import
)
from auth_service.services.model_import_service import AuthService
from platform_settings.services.import_service import CallBalanceServiceLoader

logger = logging.getLogger(__name__)

call_cost = Decimal("1.00")  # Flat cost per call

class CallService:
    def __init__(self, user):
        if not user:
            raise ValidationException(
                detail="User is required",
                context={'user': 'User parameter cannot be None'}
            )
        
        self.user = user

    _call_record = None
    _call_event_log = None

    @classmethod
    def get_call_record_model(cls):
        if cls._call_record is None:
            cls._call_record = apps.get_model('call_service', 'CallRecord')
        return cls._call_record
    
    @classmethod
    def get_call_event_log_model(cls):
        if cls._call_event_log is None:
            cls._call_event_log = apps.get_model('call_service', 'CallEventLog')
        return cls._call_event_log

    def handle_event(self, event_name, data, request=None):
        """Handle call events with comprehensive analytics"""
        # Input validation
        if not event_name or not isinstance(event_name, str):
            raise ValidationException(
                detail="Invalid event name",
                context={'event_name': 'Event name must be a non-empty string'}
            )
        
        if not data or not isinstance(data, dict):
            raise ValidationException(
                detail="Invalid event data",
                context={'data': 'Event data must be a dictionary'}
            )
        
        call_id = data.get("call_id")
        if not call_id:
            raise ValidationException(
                detail="Missing call ID",
                context={'call_id': 'call_id is required in event data'}
            )

        # Get IP address from request
        ip_address = self._get_client_ip(request) if request else None

        try:
            with transaction.atomic():
                # Get or create call record
                call = self._get_or_create_call(call_id, data, ip_address)
                
                # Log the event
                self._log_event(call, event_name, data, ip_address)
                
                # Update call state based on event
                previous_state = call.state
                self._update_call_state(call, event_name, data)
                
                # Handle call ending and potential balance deduction
                if event_name in ["onCallEnd", "onHangUp"]:
                    self._handle_call_end(call, data, previous_state)
                
                # Save call updates
                call.save()
                
                # Update cache
                self._update_call_cache(call)
                
                return call

        except ValidationException:
            raise
        except InsufficientBalanceException:
            raise
        except AuthenticationException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error handling call event {event_name}: {str(e)}")
            raise ServiceUnavailableException(
                detail="Call event database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to handle call event {event_name}: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Call event service temporarily unavailable",
                context={
                    'event_name': event_name,
                    'user_message': 'Unable to process call event. Please try again.'
                }
            )

    def _get_or_create_call(self, call_id, data, ip_address):
        """Get existing call or create new one with proper participant mapping and balance check"""
        CallRecord = self.get_call_record_model()
        User = AuthService.get_user_model()
        
        try:
            return CallRecord.objects.select_for_update().get(call_id=call_id)
        except CallRecord.DoesNotExist:
            # Extract participant IDs
            inviter_id = data.get("sender_id") or str(self.user.user_id)
            invitee_id = data.get("receiver_id")
            
            if not invitee_id:
                raise ValidationException(
                    detail="Missing receiver ID",
                    context={'receiver_id': 'receiver_id is required for new calls'}
                )
            
            # Prevent self-calling
            if inviter_id == invitee_id:
                raise ValidationException(
                    detail="Invalid call participants",
                    context={'participants': 'Cannot call yourself'}
                )
            
            try:
                inviter = User.objects.get(user_id=inviter_id)
                invitee = User.objects.get(user_id=invitee_id)
            except User.DoesNotExist as e:
                raise ValidationException(
                    detail="Call participant not found",
                    context={'participants': f'User not found: {str(e)}'}
                )
            
            
            # Check if inviter is allowed to call
            if not self._can_user_call(inviter, invitee):
                raise ValidationException(
                    detail="Call not permitted",
                    context={'call_restriction': 'Call not allowed between these users'}
                )

            # Check inviter balance before allowing call initiation
            try:
                CallBalanceService = CallBalanceServiceLoader.get_call_balance_service()
                inviter_balance = CallBalanceService.get_user_balance(inviter)
                if inviter_balance.total_balance < call_cost:
                    raise InsufficientBalanceException(
                        detail="Insufficient balance to initiate call",
                        context={
                            'required': str(call_cost),
                            'available': str(inviter_balance.total_balance),
                            'user_id': inviter.user_id
                        }
                    )
            except ImportError:
                logger.warning("CallBalanceService not available, skipping balance check")

            try:
                # Create new call record
                call = CallRecord(
                    call_id=call_id,
                    inviter=inviter,
                    invitee=invitee,
                    call_type=data.get("type", "audio"),
                    custom_data=data.get("custom_data", {}),
                    inviter_ip=ip_address if str(self.user.user_id) == inviter_id else None,
                    initiated_at=timezone.now()
                )
                call.save()
                logger.info(f"Created new call record: {call_id}")
                return call
                
            except IntegrityError as e:
                logger.error(f"Integrity error creating call record: {str(e)}")
                raise ConflictException(
                    detail="Call creation conflict",
                    context={'call_id': call_id}
                )

        except ValidationException:
            raise
        except InsufficientBalanceException:
            raise
        except ConflictException:
            raise
        except DatabaseError as e:
            logger.error(f"Database error getting/creating call: {str(e)}")
            raise ServiceUnavailableException(
                detail="Call database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Unexpected error getting/creating call: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Call creation service temporarily unavailable"
            )
        
    def _can_user_call(self, inviter, invitee):
        """Check if user is allowed to make calls"""
        # Add any business logic here (blocked users, restrictions, etc.)
        return True

    def _log_event(self, call, event_name, data, ip_address):
        """Log detailed call event"""
        try:
            CallEventLog = self.get_call_event_log_model()
            CallEventLog.objects.create(
                call=call,
                event_type=event_name,
                event_data=data,
                triggered_by=self.user,
                ip_address=ip_address,
                timestamp=timezone.now()
            )
        except DatabaseError as e:
            logger.error(f"Database error logging call event: {str(e)}")
            # Don't fail the call for logging errors, just log the issue
        except Exception as e:
            logger.error(f"Failed to log call event: {str(e)}")

    def _update_call_state(self, call, event_name, data):
        """Update call state based on event with timing analytics"""
        valid_events = [
            "onIncomingCallReceived", "onIncomingCallAcceptButtonPressed",
            "onOutgoingCallAccepted", "onIncomingCallDeclineButtonPressed",
            "onOutgoingCallDeclined", "onOutgoingCallRejectedCauseBusy",
            "onOutgoingCallCancelButtonPressed", "onIncomingCallCanceled",
            "onOutgoingCallTimeout", "onIncomingCallTimeout", "onCallEnd", "onHangUp"
        ]
        
        if event_name not in valid_events:
            logger.warning(f"Unknown call event: {event_name}")
            return

        state_mapping = {
            "onIncomingCallReceived": ("ringing", self._set_ringing_time),
            "onIncomingCallAcceptButtonPressed": ("accepted", self._set_accepted_time),
            "onOutgoingCallAccepted": ("accepted", self._set_accepted_time),
            "onIncomingCallDeclineButtonPressed": ("rejected", self._set_rejected_time),
            "onOutgoingCallDeclined": ("rejected", self._set_rejected_time),
            "onOutgoingCallRejectedCauseBusy": ("busy", None),
            "onOutgoingCallCancelButtonPressed": ("canceled", None),
            "onIncomingCallCanceled": ("canceled", None),
            "onOutgoingCallTimeout": ("missed", None),
            "onIncomingCallTimeout": ("missed", None),
            "onCallEnd": ("ended", None),
            "onHangUp": ("ended", None),
        }

        if event_name in state_mapping:
            new_state, time_handler = state_mapping[event_name]

            # Update state
            call.previous_state = call.state
            call.state = new_state

            # Apply timing handler if defined
            if time_handler:
                try:
                    time_handler(call)
                except Exception as e:
                    logger.error(f"Error in time handler for {event_name}: {str(e)}")

            # Calculate response metrics
            self._calculate_response_metrics(call)

            # Save changes
            try:
                call.save()
            except DatabaseError as e:
                logger.error(f"Database error updating call state: {str(e)}")
                raise ServiceUnavailableException(
                    detail="Call state update database temporarily unavailable"
                )

    # ... [Other helper methods remain similar with error handling] ...

    def _deduct_call_cost(self, call):
        """Deduct flat cost of 1 from inviter using CallBalanceService"""
        try:
            CallBalanceService = CallBalanceServiceLoader.get_call_balance_service()
            CallBalanceService.deduct_call_cost(call.inviter, call_cost, call)
            logger.info(f"Successfully deducted {call_cost} for call {call.call_id}")
        except ImportError as e:
            call.deduction_status = 'failed'
            logger.error(f"CallBalanceService not available: {str(e)}")
        except InsufficientBalanceException:
            call.deduction_status = 'failed'
            logger.warning(f"Insufficient balance for call deduction: {call.inviter.user_id}")
        except Exception as e:
            call.deduction_status = 'failed'
            logger.error(f"Unexpected error during deduction for call {call.call_id}: {str(e)}")

    def _update_call_cache(self, call, timeout=CACHE_TTL):
        """Update call cache with current state and inviter's latest balance"""
        try:
            CallBalanceService = CallBalanceServiceLoader.get_call_balance_service()
            balance = CallBalanceService.get_user_balance(call.inviter)

            set_call_cache(
                call.call_id,
                {
                    "call_id": call.call_id,
                    "inviter_id": call.inviter_id,
                    "invitee_id": call.invitee_id,
                    "state": call.state,
                    "duration": call.duration,
                    "initiated_at": call.initiated_at.isoformat() if call.initiated_at else None,
                    "accepted_at": call.accepted_at.isoformat() if call.accepted_at else None,
                    "ended_at": call.ended_at.isoformat() if call.ended_at else None,
                    "deduction_status": call.deduction_status,
                    "deducted_from_bonus": str(getattr(call, "deducted_from_bonus", 0)),
                    "deducted_from_base": str(getattr(call, "deducted_from_base", 0)),
                    "balance": {
                        "base_balance": str(balance.base_balance),
                        "bonus_balance": str(balance.bonus_balance),
                        "total_balance": str(balance.total_balance),
                    },
                },
                timeout=timeout
            )
        except Exception as e:
            logger.error(f"Failed to update call cache: {str(e)}")
            # Don't fail the call for cache errors

    def _get_client_ip(self, request):
        """Get client IP address from request"""
        try:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                return x_forwarded_for.split(',')[0].strip()
            return request.META.get('REMOTE_ADDR')
        except Exception as e:
            logger.error(f"Error getting client IP: {str(e)}")
            return None

class CallReconciliationService:

    _call_record = None

    @classmethod
    def get_call_record_model(cls):
        if cls._call_record is None:
            cls._call_record = apps.get_model('call_service', 'CallRecord')
        return cls._call_record
    
    @classmethod
    def reconcile_failed_deductions(cls):
        """Retry failed call cost deductions"""
        CallRecord = cls.get_call_record_model()
        
        try:
            failed_calls = CallRecord.objects.filter(
                deduction_status="failed",
                was_connected=True,
                duration__gt=0
            ).select_related('inviter')

            reconciled, still_failed = 0, 0

            for call in failed_calls:
                if not call.inviter or not call.inviter.is_regular_user():
                    logger.error(f"Skipping invalid inviter for call {call.call_id}")
                    still_failed += 1
                    continue
                
                try:
                    CallBalanceService = CallBalanceServiceLoader.get_call_balance_service()
                    
                    # Check current balance
                    current_balance = CallBalanceService.get_user_balance(call.inviter)
                    if current_balance.total_balance >= call_cost:
                        CallBalanceService.deduct_call_cost(call.inviter, call_cost, call)
                        reconciled += 1
                        logger.info(f"Reconciliation succeeded for call {call.call_id}")
                    else:
                        still_failed += 1
                        logger.warning(
                            f"User {call.inviter.user_id} still has insufficient balance "
                            f"for call {call.call_id}"
                        )
                        
                except ImportError:
                    logger.error("CallBalanceService not available for reconciliation")
                    still_failed += 1
                except Exception as e:
                    still_failed += 1
                    logger.error(f"Error reconciling call {call.call_id}: {str(e)}")

            return {
                "total_processed": failed_calls.count(),
                "reconciled": reconciled,
                "still_failed": still_failed,
            }
            
        except DatabaseError as e:
            logger.error(f"Database error during reconciliation: {str(e)}")
            raise ServiceUnavailableException(
                detail="Reconciliation database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Reconciliation service failed: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Call reconciliation service temporarily unavailable"
            )

class CallAnalyticsService:
    """Service for call analytics and reporting"""

    _call_record = None

    @classmethod
    def get_call_record_model(cls):
        if cls._call_record is None:
            cls._call_record = apps.get_model('call_service', 'CallRecord')
        return cls._call_record
    
    @classmethod
    def get_user_call_stats(cls, user_id):
        """Get comprehensive call statistics for a user"""
        # Input validation
        if not user_id:
            raise ValidationException(
                detail="User ID is required",
                context={'user_id': 'User ID cannot be empty'}
            )

        CallRecord = cls.get_call_record_model()
        User = AuthService.get_user_model()

        try:
            user = User.objects.get(user_id=user_id)

            
            # Get call statistics
            calls = CallRecord.objects.filter(
                Q(inviter=user) | Q(invitee=user)
            )
            
            stats = calls.aggregate(
                total_calls=Count('id'),
                outgoing_calls=Count('id', filter=Q(inviter=user)),
                incoming_calls=Count('id', filter=Q(invitee=user)),
                connected_calls=Count('id', filter=Q(was_connected=True)),
                total_duration=Sum('duration', filter=Q(was_connected=True)),
                average_duration=Avg('duration', filter=Q(was_connected=True)),
                missed_calls=Count('id', filter=Q(state='missed')),
                rejected_calls=Count('id', filter=Q(state='rejected')),
                average_rating=Avg('call_quality_rating')
            )
            
            # Get recent call activity
            recent_calls = calls.order_by('-initiated_at')[:5]
            recent_activity = [
                {
                    'call_id': call.call_id,
                    'type': 'outgoing' if call.inviter == user else 'incoming',
                    'state': call.state,
                    'duration': call.duration,
                    'timestamp': call.initiated_at,
                    'other_party': call.invitee.user_name if call.inviter == user else call.inviter.user_name
                }
                for call in recent_calls
            ]
            
            return {
                **stats,
                'recent_activity': recent_activity,
                'user_id': user_id,
                'user_name': user.user_name
            }
            
        except User.DoesNotExist:
            raise NotFoundException(  # Fixed - use NotFoundException
                detail="User not found",
                context={'user_id': f'No user found with ID: {user_id}'}
            )
        except DatabaseError as e:
            logger.error(f"Database error getting call stats: {str(e)}")
            raise ServiceUnavailableException(
                detail="Call analytics database temporarily unavailable"
            )
        except Exception as e:
            logger.error(f"Failed to get user call stats: {str(e)}", exc_info=True)
            raise ServiceUnavailableException(
                detail="Call analytics service temporarily unavailable",
                context={
                    'user_message': 'Unable to load call statistics. Please try again.'
                }
            )