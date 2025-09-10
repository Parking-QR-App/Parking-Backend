from call_service.models import CallRecord, CallEventLog
from django.utils import timezone
from utils.cache import set_call_cache, CACHE_TTL
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from decimal import Decimal
from django.db.models import Q, Count, Sum, Avg
import logging
from shared.utils.api_exceptions import (ValidationException, InsufficientBalanceException,
                                         ResourceNotFoundException, ServiceUnavailableException)

User = get_user_model()
logger = logging.getLogger(__name__)

call_cost = Decimal("1.00")  # Flat cost per call

class CallService:
    def __init__(self, user):
        self.user = user

    def handle_event(self, event_name, data, request=None):
        """Handle call events with comprehensive analytics"""
        call_id = data.get("call_id")
        if not call_id:
            raise ValidationException(detail="call_id is required")

        # Get IP address from request
        ip_address = self._get_client_ip(request) if request else None

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

    def _get_or_create_call(self, call_id, data, ip_address):
        """Get existing call or create new one with proper participant mapping and balance check"""
        try:
            return CallRecord.objects.select_for_update().get(call_id=call_id)
        except CallRecord.DoesNotExist:
            # Extract participant IDs
            inviter_id = data.get("sender_id") or str(self.user.user_id)
            invitee_id = data.get("receiver_id")
            
            if not invitee_id:
                raise ValidationException(detail="receiver_id is required")
            
            # Prevent self-calling
            if inviter_id == invitee_id:
                raise ValidationException(detail="Cannot call yourself")
            
            try:
                inviter = User.objects.get(user_id=inviter_id)
                invitee = User.objects.get(user_id=invitee_id)
            except ObjectDoesNotExist as e:
                raise ValidationException(detail=f"User not found: {str(e)}")
            
            # Check if inviter is allowed to call (not blocked, etc.)
            if not self._can_user_call(inviter, invitee):
                raise ValidationException(detail="Call not allowed")

            # Check inviter balance before allowing call initiation
            try:
                from importlib import import_module
                CallBalanceService = import_module('platform_settings.services').CallBalanceService
                inviter_balance = CallBalanceService.get_user_balance(inviter)
                if inviter_balance.total_balance < call_cost:
                    raise InsufficientBalanceException(
                        detail=f"Insufficient balance to initiate call. Required: {call_cost}",
                        context={'user_id': inviter.user_id}
                    )
            except ImportError:
                logger.warning("CallBalanceService not available, skipping balance check")

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
            return call
        
    def _can_user_call(self, inviter, invitee):
        """Check if user is allowed to make calls"""
        # Add any business logic here (blocked users, restrictions, etc.)
        return True

    def _log_event(self, call, event_name, data, ip_address):
        """Log detailed call event"""
        CallEventLog.objects.create(
            call=call,
            event_type=event_name,
            event_data=data,
            triggered_by=self.user,
            ip_address=ip_address,
            timestamp=timezone.now()
        )

    def _update_call_state(self, call, event_name, data):
        """Update call state based on event with timing analytics and cost deduction"""
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
                time_handler(call)

            # Calculate extra response metrics
            self._calculate_response_metrics(call)

            # Handle call ending → duration + cost deduction
            if new_state == "ended":
                call.ended_at = timezone.now()
                if call.accepted_at:
                    call.duration = int((call.ended_at - call.accepted_at).total_seconds())
                    call.was_connected = True
                else:
                    call.was_connected = False

                call.save()

                if call.was_connected and call.deduction_status == "pending":
                    try:
                        # Lazy import to avoid circular dependencies
                        from importlib import import_module
                        CallBalanceService = import_module('platform_settings.services').CallBalanceService
                        CallBalanceService.deduct_call_cost(call.inviter, call_cost, call)
                    except InsufficientBalanceException:
                        call.deduction_status = "failed"
                        call.notes = "Insufficient balance"
                        call.save(update_fields=["deduction_status", "notes"])
                    except Exception as e:
                        call.deduction_status = "failed"
                        call.notes = f"Deduction error: {str(e)}"
                        call.save(update_fields=["deduction_status", "notes"])

        # Always persist changes
        call.save()


    def _set_ringing_time(self, call):
        """Set ringing time and calculate initial response time"""
        if not call.ringing_at:
            call.ringing_at = timezone.now()
            if call.initiated_at:
                call.response_time = int((call.ringing_at - call.initiated_at).total_seconds())

    def _set_accepted_time(self, call):
        """Set accepted time and calculate ring duration"""
        if not call.accepted_at:
            call.accepted_at = timezone.now()
            if call.ringing_at:
                call.ring_duration = int((call.accepted_at - call.ringing_at).total_seconds())

    def _calculate_response_metrics(self, call):
        """Calculate various response time metrics"""
        if call.ringing_at and call.initiated_at:
            call.response_time = int((call.ringing_at - call.initiated_at).total_seconds())
        
        if call.accepted_at and call.ringing_at:
            call.ring_duration = int((call.accepted_at - call.ringing_at).total_seconds())

    def _set_rejected_time(self, call):
        """Set rejected time"""
        if not call.rejected_at:
            call.rejected_at = timezone.now()

    def _handle_call_end(self, call, data, previous_state):
        """Handle call ending and process balance deduction if applicable"""
        call.ended_at = timezone.now()
        call.was_connected = previous_state == 'accepted'

        if call.accepted_at and call.ended_at:
            call.duration = (call.ended_at - call.accepted_at).total_seconds()

        if isinstance(data, dict):
            call.custom_data['end_reason'] = data.get('reason')
            call.custom_data['end_metadata'] = data

        # Deduct balance only if call should be charged
        if call.should_charge and call.deduction_status == 'pending':
            self._deduct_call_cost(call)
        else:
            call.deduction_status = 'not_applicable'

    def _deduct_call_cost(self, call):
        """Deduct flat cost of 1 from inviter using CallBalanceService"""
        try:
            # Lazy import to avoid circular dependencies
            from importlib import import_module
            CallBalanceService = import_module('platform_settings.services').CallBalanceService
            CallBalanceService.deduct_call_cost(call.inviter, call_cost, call)
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
        # Lazy import to avoid circular dependencies
        from importlib import import_module
        CallBalanceService = import_module('platform_settings.services').CallBalanceService
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
                # latest balance snapshot
                "balance": {
                    "base_balance": str(balance.base_balance),
                    "bonus_balance": str(balance.bonus_balance),
                    "total_balance": str(balance.total_balance),
                },
            },
            timeout=timeout
        )

    def _get_client_ip(self, request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

class CallReconciliationService:
    @staticmethod
    def reconcile_failed_deductions():
        """
        Retry failed call cost deductions.
        Runs as part of scheduled tasks or manual admin-triggered process.
        """
        failed_calls = CallRecord.objects.filter(
            deduction_status="failed",
            was_connected=True,
            duration__gt=0
        ).select_related('inviter')

        reconciled, still_failed = 0, 0

        for call in failed_calls:
            try:
                
                # Lazy import to avoid circular dependencies
                from importlib import import_module
                CallBalanceService = import_module('platform_settings.services').CallBalanceService
                
                # Check current balance
                current_balance = CallBalanceService.get_user_balance(call.inviter)
                if current_balance.total_balance >= call_cost:
                    CallBalanceService.deduct_call_cost(call.inviter, call_cost, call)
                    reconciled += 1
                    logger.info(f"[Reconciliation] Deduction succeeded for call {call.call_id}")
                else:
                    still_failed += 1
                    logger.warning(
                        f"[Reconciliation] User {call.inviter.user_id} still has insufficient balance "
                        f"for call {call.call_id}"
                    )
                    
            except ImportError:
                logger.error("[Reconciliation] CallBalanceService not available")
                still_failed += 1
            except Exception as e:
                still_failed += 1
                logger.error(f"[Reconciliation] Error reconciling call {call.call_id}: {str(e)}")

        return {
            "total_processed": failed_calls.count(),
            "reconciled": reconciled,
            "still_failed": still_failed,
        }


class CallAnalyticsService:
    """Service for call analytics and reporting"""
    
    @staticmethod
    def get_user_call_stats(user_id):
        """Get comprehensive call statistics for a user"""
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
            raise ResourceNotFoundException(
                detail="User not found",
                context={'user_id': user_id}
            )
        except Exception as e:
            logger.error(f"Failed to get user call stats: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve call statistics",
                context={'user_id': user_id, 'error': str(e)}
            )