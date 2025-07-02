from call_service.models import CallRecord
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from utils.cache import set_call_cache, get_call_cache, delete_call_cache
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError

User = get_user_model()


class CallService:
    def __init__(self, user):
        self.user = user  # logged-in user from view or socket consumer

    def handle_event(self, event_name, data):
        call_id = data.get("call_id")
        if not call_id:
            raise ValueError("call_id is required")

        inviter_user_id = data.get("sender_id")
        invitee_user_id = data.get("receiver_id")

        # Handle inviter fallback to self.user
        if inviter_user_id:
            try:
                inviter = User.objects.get(user_id=inviter_user_id)
            except ObjectDoesNotExist:
                raise ValueError(f"Inviter with user_id {inviter_user_id} does not exist")
        else:
            inviter = self.user

        if not invitee_user_id:
            raise ValueError("invitee_user_id is required")

        try:
            invitee = User.objects.get(user_id=invitee_user_id)
        except ObjectDoesNotExist:
            raise ValueError(f"Invitee with user_id {invitee_user_id} does not exist")

        # Map of frontend event -> DB state
        state_map = {
            "onIncomingCallAcceptButtonPressed": "accepted",
            "onIncomingCallDeclineButtonPressed": "rejected",
            "onOutgoingCallCancelButtonPressed": "canceled",
            "onIncomingCallReceived": "incoming",
            "onOutgoingCallAccepted": "accepted",
            "onOutgoingCallDeclined": "rejected",
            "onOutgoingCallRejectedCauseBusy": "busy",
            "onOutgoingCallTimeout": "missed",
            "onIncomingCallTimeout": "missed",
            "onCallEnd": "ended",
            "onHangUp": "ended"
        }

        new_state = state_map.get(event_name)

        # STEP 1: Try fetching from cache
        call_data = get_call_cache(call_id)
        call = None

        if call_data:
            try:
                call = CallRecord.objects.get(call_id=call_data["call_id"])
            except CallRecord.DoesNotExist:
                call = CallRecord(
                    call_id=call_data["call_id"],
                    inviter_id=call_data["inviter_id"],
                    invitee_id=call_data["invitee_id"],
                    call_type=call_data["call_type"],
                    custom_data=call_data.get("custom_data", {}),
                    state=call_data["state"],
                    created_at=parse_datetime(call_data["created_at"]) if isinstance(call_data.get("created_at"), str) else None,
                    updated_at=parse_datetime(call_data["updated_at"]) if isinstance(call_data.get("updated_at"), str) else None,
                    ended_at=parse_datetime(call_data["ended_at"]) if isinstance(call_data.get("ended_at"), str) else None,
                    duration=call_data.get("duration"),
                    was_connected=call_data.get("was_connected", False),
                )
                call.save()  # insert only if not already in DB
        else:
            # STEP 2: Fallback to DB get_or_create
            try:
                call, created = CallRecord.objects.get_or_create(
                    call_id=call_id,
                    defaults={
                        "inviter": inviter,
                        "invitee": invitee,
                        "call_type": data.get("type", "audio"),
                        "custom_data": data.get("custom_data", {}),
                        "state": "initiated",
                    },
                )
            except IntegrityError:
                # Another request already created it — recover
                call = CallRecord.objects.get(call_id=call_id)

        # STEP 3: Update call record state if necessary
        if new_state:
            if call.state != new_state or event_name == "onCallEnd":
                call.state = new_state
                call.updated_at = timezone.now()

                if event_name == "onCallEnd":
                    duration = data.get("duration")
                    if duration is not None:
                        call.duration = int(duration)
                        call.was_connected = int(duration) > 0
                        call.ended_at = timezone.now()

                call.save()

        # STEP 4: Update cache
        set_call_cache(
            call.call_id,
            {
                "call_id": call.call_id,
                "inviter_id": call.inviter_id,
                "invitee_id": call.invitee_id,
                "call_type": call.call_type,
                "custom_data": call.custom_data,
                "state": call.state,
                "duration": call.duration,
                "created_at": call.created_at.isoformat() if call.created_at else None,
                "updated_at": call.updated_at.isoformat() if call.updated_at else None,
                "ended_at": call.ended_at.isoformat() if call.ended_at else None,
                "was_connected": call.was_connected,
            },
        )

        return call
