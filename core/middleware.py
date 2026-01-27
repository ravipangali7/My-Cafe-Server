from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse, HttpResponse
from django.conf import settings

class DisableCSRFForAPI(MiddlewareMixin):
    """Middleware to disable CSRF for all /api/ endpoints and ensure CORS headers"""
    
    def process_request(self, request):
        if request.path.startswith('/api/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
        return None
    
    def _get_http_response(self, response):
        """Get the underlying Django HttpResponse from REST Framework Response if needed"""
        # REST Framework Response extends Django's SimpleTemplateResponse/HttpResponse
        # We can set headers directly, but may need to render first for some operations
        # For setting headers and cookies, we can work directly with the response object
        return response
    
    def _set_cors_headers(self, request, response):
        """Manually set CORS headers for API responses"""
        origin = request.META.get('HTTP_ORIGIN', '')
        
        # Check if origin is in allowed origins
        allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
        if origin in allowed_origins:
            response['Access-Control-Allow-Origin'] = origin
        elif origin and getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
            response['Access-Control-Allow-Origin'] = origin
        
        # Set credentials header if CORS credentials are enabled
        if getattr(settings, 'CORS_ALLOW_CREDENTIALS', False):
            response['Access-Control-Allow-Credentials'] = 'true'
        
        # Expose Set-Cookie header so browser can read it
        response['Access-Control-Expose-Headers'] = 'Set-Cookie'
    
    def process_response(self, request, response):
        if request.path.startswith('/api/'):
            # Get the actual HTTP response object
            http_response = self._get_http_response(response)
            
            # Set CORS headers manually
            self._set_cors_headers(request, http_response)
            
            # Ensure session cookie is set for API endpoints if session exists
            if hasattr(request, 'session') and request.session.session_key:
                # Get the session cookie name from settings (defaults to 'sessionid')
                cookie_name = getattr(settings, 'SESSION_COOKIE_NAME', 'sessionid')
                # Manually set the session cookie if it's not already set
                if cookie_name not in http_response.cookies:
                    session_key = request.session.session_key
                    if session_key:
                        # Set cookie with proper attributes for CORS
                        http_response.set_cookie(
                            cookie_name,
                            session_key,
                            max_age=settings.SESSION_COOKIE_AGE,
                            path=settings.SESSION_COOKIE_PATH,
                            domain=settings.SESSION_COOKIE_DOMAIN,
                            secure=settings.SESSION_COOKIE_SECURE,
                            httponly=settings.SESSION_COOKIE_HTTPONLY,
                            samesite=settings.SESSION_COOKIE_SAMESITE
                        )
        
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
