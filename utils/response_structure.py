from rest_framework import status
from rest_framework.response import Response
# utils/response.py
def success_response(message, data=None, status=status.HTTP_200_OK):
    return Response({
        'message': message,
        'data': data or {},
        'status': status
    }, status=status)

def error_response(message, errors, status):
    return Response({
        'message': message,
        'errors': errors,
        'status': status
    }, status=status)