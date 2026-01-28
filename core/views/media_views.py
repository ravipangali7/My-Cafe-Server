"""
Serve media files with CORS headers for cross-origin access (e.g. frontend at mycafe.sewabyapar.com
fetching logos from mycafeserver.sewabyapar.com). No auth, CSRF, or login required.
"""
import os
from django.conf import settings
from django.http import FileResponse, Http404


def serve_media_cors(request, path):
    """
    Serve a file from MEDIA_ROOT under the given path. Sets CORS headers so the
    frontend origin can load images/files cross-origin. No authentication.
    """
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
    # Set CORS so frontend can use the resource cross-origin
    origin = request.META.get("HTTP_ORIGIN", "")
    allowed = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    if origin in allowed:
        response["Access-Control-Allow-Origin"] = origin
    elif allowed:
        # Fallback: allow first configured origin (e.g. frontend)
        response["Access-Control-Allow-Origin"] = allowed[0]
    if getattr(settings, "CORS_ALLOW_CREDENTIALS", False):
        response["Access-Control-Allow-Credentials"] = "true"

    # Optional: allow cache for static media
    response.setdefault("Cache-Control", "public, max-age=86400")
    return response
