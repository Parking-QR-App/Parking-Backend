from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.throttling import BaseThrottle
from rest_framework.exceptions import Throttled
from django.core.cache import cache
from rest_framework import status, generics
from django.db.models import Q, Sum, Count, Avg
from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework.response import Response

from .services.call_service import CallService, CallAnalyticsService
from .models import CallRecord
from .serializers import (
    CallRecordSerializer, CallRatingSerializer,
    CallAnalyticsSerializer, CallDetailSerializer
)
from shared.utils.api_exceptions import (
    InvalidRequestException, ResourceNotFoundException,
    ServiceUnavailableException, ValidationException,
    PermissionDeniedException
)
from utils.response_structure import success_response
import logging

logger = logging.getLogger(__name__)

CACHE_PREFIX = "scanqr_cache"

class CallEventThrottle(BaseThrottle):
    """
    Optimal throttling for call events:
    - Strict for call initiation
    - Generous for other events
    """
    
    def allow_request(self, request, view):
        event_name = request.data.get('event')
        call_id = request.data.get('data', {}).get('call_id')
        user_id = str(request.user.user_id)
        
        # 1. Strict for call initiation
        if event_name in ['onIncomingCallReceived', 'onOutgoingCallAccepted']:
            return self._throttle_call_initiation(user_id)
        
        # 2. Generous for other call events
        if call_id:
            return self._throttle_call_events(call_id)
        
        # 3. Lenient fallback for malformed requests
        logger.warning(f"Malformed call event request: {request.data}")
        return True

    def _throttle_call_initiation(self, user_id):
        """Allow max 5 initiations per minute per user"""
        key = f"{CACHE_PREFIX}_call_init_{user_id}"
        
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=60)
        
        count = cache.get(key, 0)
        if count > 5:
            return False
        return True

    def _throttle_call_events(self, call_id):
        """Allow max 100 events per 5 minutes per call"""
        key = f"{CACHE_PREFIX}_call_events_{call_id}"
        
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=300)
        
        count = cache.get(key, 0)
        if count > 100:
            return False
        return True

    def wait(self):
        """Suggest retry time"""
        return 30

class CallEventAPIView(APIView):
    """Handle call events from external systems"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [CallEventThrottle]

    def post(self, request):
        try:
            event_name = request.data.get("event")
            if not event_name:
                raise InvalidRequestException(
                    detail="Missing event parameter",
                    context={'required_field': 'event'}
                )

            valid_events = [
                "onIncomingCallReceived", "onIncomingCallAcceptButtonPressed",
                "onOutgoingCallAccepted", "onIncomingCallDeclineButtonPressed",
                "onOutgoingCallDeclined", "onOutgoingCallRejectedCauseBusy",
                "onOutgoingCallCancelButtonPressed", "onIncomingCallCanceled",
                "onOutgoingCallTimeout", "onIncomingCallTimeout", "onCallEnd", "onHangUp"
            ]
            
            if event_name not in valid_events:
                raise ValidationException(
                    detail="Invalid event type",
                    context={'event_name': event_name, 'valid_events': valid_events}
                )

            service = CallService(request.user)
            call = service.handle_event(
                event_name, 
                request.data.get('data', {}), 
                request
            )

            return success_response(
                message="Call event processed successfully",
                data={
                    "call_id": call.call_id,
                    "state": call.state,
                    "duration": call.duration,
                    "deduction_status": call.deduction_status
                },
                status=status.HTTP_200_OK
            )

        except Throttled as e:
            return Response({
                'error': 'Too many requests',
                'message': 'Please wait before making more calls',
                'retry_after': e.wait or 30
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        except ValidationException as e:
            raise
        except ResourceNotFoundException as e:
            raise
        except Exception as e:
            logger.error(f"Failed to process call event: {str(e)}")
            raise ServiceUnavailableException(
                detail="Unable to process call event",
                context={
                    'error': str(e),
                    'event_name': event_name,
                    'user_id': str(request.user.user_id)
                }
            )
            
class CallRatingAPIView(APIView):
    """Handle call ratings and feedback"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            serializer = CallRatingSerializer(data=request.data)
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid rating data",
                    context=serializer.errors
                )
            
            data = serializer.validated_data
            call_id = data['call_id']
            rating = data['rating']
            feedback = data.get('feedback', '')
            
            # Get call record
            try:
                call = CallRecord.objects.get(call_id=call_id)
            except CallRecord.DoesNotExist:
                raise ResourceNotFoundException(
                    detail="Call not found",
                    context={'call_id': call_id}
                )
            
            # Check if user participated in this call
            if request.user not in [call.inviter, call.invitee]:
                raise PermissionDeniedException(
                    detail="User did not participate in this call",
                    context={
                        'call_id': call_id,
                        'user_id': str(request.user.user_id)
                    }
                )
            
            # Update rating based on user role
            if request.user == call.inviter:
                call.inviter_rating = rating
                call.inviter_feedback = feedback
            else:
                call.invitee_rating = rating
                call.invitee_feedback = feedback
            
            # Calculate average rating
            ratings = [r for r in [call.inviter_rating, call.invitee_rating] if r is not None]
            if ratings:
                call.call_quality_rating = sum(ratings) / len(ratings)
            
            call.save()
            
            return success_response(
                message="Call rating submitted successfully",
                data={
                    'call_id': call_id,
                    'rating': rating,
                    'average_rating': call.call_quality_rating
                },
                status=status.HTTP_200_OK
            )
            
        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"Failed to submit call rating: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to submit call rating",
                context={
                    'error': str(e),
                    'call_id': request.data.get('call_id', 'unknown')
                }
            )

class CallAnalyticsAPIView(APIView):
    """Get call analytics for authenticated user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            stats = CallAnalyticsService.get_user_call_stats(request.user.user_id)
            
            # Calculate cost analytics
            cost_stats = CallRecord.objects.filter(
                Q(inviter=request.user) | Q(invitee=request.user),
                deduction_status='completed'
            ).aggregate(
                total_cost=Sum('call_cost'),
                bonus_used=Sum('deducted_from_bonus'),
                base_used=Sum('deducted_from_base')
            )
            
            analytics_data = {
                **stats,
                'total_cost': cost_stats['total_cost'] or Decimal('0.00'),
                'bonus_balance_used': cost_stats['bonus_used'] or Decimal('0.00'),
                'base_balance_used': cost_stats['base_used'] or Decimal('0.00')
            }
            
            serializer = CallAnalyticsSerializer(analytics_data)
            
            return success_response(
                message="Call analytics retrieved successfully",
                data=serializer.data,
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve call analytics: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve call analytics",
                context={
                    'error': str(e),
                    'user_id': str(request.user.user_id)
                }
            )

class CallHistoryAPIView(generics.ListAPIView):
    """Get call history for authenticated user"""
    permission_classes = [IsAuthenticated]
    serializer_class = CallRecordSerializer
    
    def get_queryset(self):
        return CallRecord.objects.filter(
            Q(inviter=self.request.user) | Q(invitee=self.request.user)
        ).select_related('inviter', 'invitee').order_by('-initiated_at')
    
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            page = self.paginate_queryset(queryset)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            return success_response(
                message="Call history retrieved successfully",
                data=serializer.data,
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve call history: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve call history",
                context={
                    'error': str(e),
                    'user_id': str(request.user.user_id)
                }
            )

class CallDetailAPIView(APIView):
    """Get detailed information about a specific call"""
    permission_classes = [IsAuthenticated]

    def get(self, request, call_id):
        try:
            call = get_object_or_404(
                CallRecord.objects.select_related('inviter', 'invitee')
                                   .prefetch_related('event_logs'),
                call_id=call_id
            )
            
            # Check if user has permission to view this call
            if request.user not in [call.inviter, call.invitee]:
                raise PermissionDeniedException(
                    detail="You don't have permission to view this call",
                    context={'call_id': call_id}
                )
            
            serializer = CallDetailSerializer(call)
            
            return success_response(
                message="Call details retrieved successfully",
                data=serializer.data,
                status=status.HTTP_200_OK
            )
            
        except CallRecord.DoesNotExist:
            raise ResourceNotFoundException(
                detail="Call not found",
                context={'call_id': call_id}
            )
        except Exception as e:
            logger.error(f"Failed to retrieve call details: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve call details",
                context={
                    'error': str(e),
                    'call_id': call_id
                }
            )

class AdminCallAnalyticsAPIView(APIView):
    """Admin view for comprehensive call analytics"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            # Get date range from query parameters
            start_date = request.query_params.get('start_date')
            end_date = request.query_params.get('end_date')
            
            # Build base queryset
            calls = CallRecord.objects.all()
            
            if start_date:
                calls = calls.filter(initiated_at__gte=start_date)
            if end_date:
                calls = calls.filter(initiated_at__lte=end_date)
            
            # Aggregate statistics
            stats = calls.aggregate(
                total_calls=Count('id'),
                connected_calls=Count('id', filter=Q(was_connected=True)),
                total_duration=Sum('duration', filter=Q(was_connected=True)),
                total_revenue=Sum('call_cost', filter=Q(deduction_status='completed')),
                average_rating=Avg('call_quality_rating', filter=Q(call_quality_rating__isnull=False))
            )
            
            # User statistics
            user_stats = calls.values('inviter').annotate(
                call_count=Count('id'),
                total_duration=Sum('duration', filter=Q(was_connected=True)),
                total_cost=Sum('call_cost', filter=Q(deduction_status='completed'))
            ).order_by('-call_count')[:10]  # Top 10 users
            
            return success_response(
                message="Admin call analytics retrieved successfully",
                data={
                    'overview': stats,
                    'top_users': list(user_stats),
                    'time_period': {
                        'start_date': start_date,
                        'end_date': end_date
                    }
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            logger.error(f"Failed to retrieve admin analytics: {str(e)}")
            raise ServiceUnavailableException(
                detail="Failed to retrieve admin call analytics",
                context={'error': str(e)}
            )

class ZegoTokenView(APIView):
    """Generate Zego tokens for voice/video calls"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            user_id = str(request.user.user_id)
            
            # Validate user_id exists
            if not user_id:
                raise InvalidRequestException(
                    detail="User ID not available",
                    context={'user': str(request.user)}
                )
            
            # Validate user has sufficient balance
            # Add logic to block token generation if balance is insufficient in case of subscriptions in future 
            # so without payment, user should not be able to receive calls or make calls
            
            # Import here to avoid circular imports
            from call_service.utils import generate_zego_token
            token = generate_zego_token(user_id=user_id)
            
            return success_response(
                message="Zego token generated successfully",
                data={
                    "zego_token": token,
                    "user_id": user_id,
                    "expires_in": 3600  # 1 hour
                },
                status=status.HTTP_200_OK
            )
            
        except InvalidRequestException:
            raise
        except Exception as e:
            logger.error(f"Failed to generate Zego token: {str(e)}")
            raise ServiceUnavailableException(
                detail="Unable to generate Zego token",
                context={
                    'error': str(e),
                    'user_id': str(request.user.user_id)
                }
            )