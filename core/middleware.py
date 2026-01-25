from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse

class DisableCSRFForAPI(MiddlewareMixin):
    """Middleware to disable CSRF for all /api/ endpoints"""
    
    def process_request(self, request):
        if request.path.startswith('/api/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        return None
    
    def process_response(self, request, response):
        # Prevent redirects for API endpoints - return JSON error instead
        if request.path.startswith('/api/') and response.status_code in [302, 301, 307, 308]:
            # For API endpoints, ANY redirect should be converted to a JSON 401 response
            # This handles cases where Django redirects for authentication or other reasons
            # The frontend will handle opaque redirects (CORS) separately
            return JsonResponse(
                {'error': 'Not authenticated'},
                status=401
            )
        return response
