"""
Serve media files with CORS headers for cross-origin access (e.g. frontend at mycafe.sewabyapar.com
fetching logos from mycafeserver.sewabyapar.com). No auth, CSRF, or login required.
"""
import os
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse


def _set_cors_headers_on_response(response, request):
    """Set CORS headers on a response using request Origin and settings."""
    origin = request.META.get("HTTP_ORIGIN", "")
    allowed = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    if origin in allowed:
        response["Access-Control-Allow-Origin"] = origin
    elif allowed:
        response["Access-Control-Allow-Origin"] = allowed[0]
    if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
        response["Access-Control-Allow-Credentials"] = "true"
    # So caches do not serve a response with wrong CORS to another origin
    response["Vary"] = "Origin"


def serve_media_cors(request, path):
    """
    Serve a file from MEDIA_ROOT under the given path. Sets CORS headers so the
    frontend origin can load images/files cross-origin. No authentication.
    Responds to OPTIONS (preflight) with CORS headers and no file read.
    """
    # OPTIONS preflight: return 204 with CORS headers only (no file open)
    if request.method == "OPTIONS":
        response = HttpResponse(status=204)
        _set_cors_headers_on_response(response, request)
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Max-Age"] = "86400"
        return response

    # Prevent directory traversal: path must not contain '..' or start with /
    if ".." in path or path.startswith("/"):
        raise Http404("Invalid path")

    media_root = os.path.normpath(settings.MEDIA_ROOT)
    full_path = os.path.normpath(os.path.join(media_root, path))

    # Ensure resolved path is still under MEDIA_ROOT
    if not full_path.startswith(media_root):
        raise Http404("Invalid path")

    if not os.path.isfile(full_path):
        raise Http404("File not found")

    response = FileResponse(open(full_path, "rb"))
    _set_cors_headers_on_response(response, request)

    # Optional: allow cache for static media
    response.setdefault("Cache-Control", "public, max-age=86400")
    return response
