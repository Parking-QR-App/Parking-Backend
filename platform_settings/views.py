from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from django.shortcuts import get_object_or_404
from django.db.models import Q

from .models import PlatformSetting, UserCallBalance, BalanceResetLog
from .serializers import (
    PlatformSettingSerializer, PlatformSettingUpdateSerializer,
    UserCallBalanceSerializer, BalanceResetLogSerializer,
    BulkBalanceUpdateSerializer, CronExecutionSerializer
)
from .services import SettingsService, CallBalanceService, DefaultSettings
from auth_service.models import User

class PlatformSettingListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PlatformSettingSerializer
    queryset = PlatformSetting.objects.all()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        return queryset.order_by('category', 'display_name')

class PlatformSettingDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = PlatformSettingSerializer
    queryset = PlatformSetting.objects.all()
    lookup_field = 'key'

    # Query Parameters:
    # category: call_management, referral_system, automation

    # search: search term

    # is_active: true/false

class UpdatePlatformSettingView(APIView):
    permission_classes = [IsAdminUser]
    
    def patch(self, request, key):
        setting = get_object_or_404(PlatformSetting, key=key)
        serializer = PlatformSettingUpdateSerializer(
            data=request.data, 
            context={'setting': setting}
        )
        
        if serializer.is_valid():
            new_value = serializer.validated_data['value']
            success = SettingsService.set_setting(key, new_value)
            
            if success:
                return Response({
                    'message': f'Setting {key} updated successfully',
                    'new_value': new_value
                })
            return Response(
                {'error': 'Failed to update setting'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserCallBalanceListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserCallBalanceSerializer
    
    def get_queryset(self):
        queryset = UserCallBalance.objects.select_related('user').all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search) | 
                Q(user__user_id__icontains=search)
            )
        return queryset.order_by('-updated_at')

class UserCallBalanceDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = UserCallBalanceSerializer
    queryset = UserCallBalance.objects.all()
    
    def get_object(self):
        user_id = self.kwargs['user_id']
        user = get_object_or_404(User, user_id=user_id)
        return get_object_or_404(UserCallBalance, user=user)

class BulkBalanceUpdateView(APIView):
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        serializer = BulkBalanceUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        updated_count = 0
        
        for user_id in data['user_ids']:
            try:
                user = User.objects.get(user_id=user_id)
                balance = CallBalanceService.get_user_balance(user)
                
                if 'base_balance' in data:
                    if data['operation'] == 'set':
                        balance.base_balance = data['base_balance']
                    elif data['operation'] == 'add':
                        balance.base_balance += data['base_balance']
                    elif data['operation'] == 'subtract':
                        balance.base_balance = max(0, balance.base_balance - data['base_balance'])
                
                if 'bonus_balance' in data:
                    if data['operation'] == 'set':
                        balance.bonus_balance = data['bonus_balance']
                    elif data['operation'] == 'add':
                        balance.bonus_balance += data['bonus_balance']
                    elif data['operation'] == 'subtract':
                        balance.bonus_balance = max(0, balance.bonus_balance - data['bonus_balance'])
                
                balance.save()
                updated_count += 1
                
            except User.DoesNotExist:
                continue
        
        return Response({
            'message': f'Updated balances for {updated_count} users',
            'updated_count': updated_count
        })

class BalanceResetLogListView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = BalanceResetLogSerializer
    queryset = BalanceResetLog.objects.select_related('user').all()
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user__user_id=user_id)
        return queryset.order_by('-created_at')

class ExecuteCronResetView(APIView):
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        serializer = CronExecutionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        if serializer.validated_data['dry_run']:
            users = CallBalanceService.get_users_for_reset()
            return Response({
                'dry_run': True,
                'eligible_users_count': len(users),
                'users': [{'id': u.id, 'email': u.email} for u in users[:10]]  # First 10 only
            })
        
        result = CallBalanceService.execute_cron_reset()
        return Response(result)

class InitializeSettingsView(APIView):
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        count = DefaultSettings.initialize()
        return Response({
            'message': f'Initialized {count} default settings',
            'count': count
        })