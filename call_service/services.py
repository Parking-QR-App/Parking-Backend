from django.utils.timezone import now
from django.shortcuts import get_object_or_404
from .models import Call
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()


def create_call(host, guest_id):
    """Creates a new Jitsi call and returns it."""
    if host.id == guest_id:
        return None, "You cannot call yourself"

    guest = get_object_or_404(User, id=guest_id)

    room_name = f"call-{uuid.uuid4().hex[:8]}"

    call = Call.objects.create(
        host=host,
        guest=guest,
        room_name=room_name,
        call_status="ongoing"
    )

    return call, None


def end_call(call, status="ended"):
    """Ends an active call."""
    if call.call_status == "ended":
        return "Call already ended"

    call.call_status = status
    call.end_time = now()
    call.save()
    return None


def get_call_history(user):
    """Fetches call history for a user."""
    return Call.objects.filter(host=user) | Call.objects.filter(guest=user)


def get_all_calls():
    """Admin function to get all calls."""
    return Call.objects.all()
