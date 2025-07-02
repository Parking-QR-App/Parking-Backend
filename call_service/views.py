from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from call_service.services.call_service import CallService
from call_service.utils import generate_zego_token

class CallEventAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        event_name = request.data.get("event")
        if not event_name:
            return Response({"error": "Missing event"}, status=400)

        try:
            service = CallService(request.user)
            print(request.data)
            call = service.handle_event(event_name, request.data['data'])

            return Response({
                "message": f"Call updated to {call.state}",
                "call_id": call.call_id,
                "state": call.state,
            })
        except Exception as e:
            print(e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ZegoTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = str(request.user.user_id)  # Assuming you store user_id in your model
        print(user_id)
        token = generate_zego_token(user_id=user_id)
        print(token)
        return Response({
            "zego_token": token,
            "user_id": user_id,
        })
