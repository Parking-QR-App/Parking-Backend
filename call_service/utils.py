from rest_framework.response import Response
from rest_framework import status

def success_response(data=None, message="Success", status_code=status.HTTP_200_OK):
    """Standardized success response."""
    return Response({
        "data": data,
        "message": message,
        "status": "success"
    }, status=status_code)


def error_response(error_message, status_code=status.HTTP_400_BAD_REQUEST):
    """Standardized error response."""
    return Response({
        "error": error_message,
        "status": "error"
    }, status=status_code)
