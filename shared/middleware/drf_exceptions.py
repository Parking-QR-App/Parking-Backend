from shared.utils.api_exceptions import format_exception_response

class DRFExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as exc:
            return format_exception_response(exc, context={"request": request})
