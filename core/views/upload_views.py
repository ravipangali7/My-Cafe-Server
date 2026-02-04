"""
Generic file upload endpoint for WebView (Flutter mobile).
Accepts a single file, saves to media/, returns URL.
Used when <input type="file"> does not work in WebView; Flutter picks file and uploads here.
"""
import os
import uuid
import logging
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

# Max file size 5MB
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'}
ALLOWED_PDF_TYPE = 'application/pdf'

UPLOAD_SUBDIRS = {
    'logo': 'logos',
    'kyc_document': 'kyc_documents',
    'whatsapp_image': 'whatsapp_notifications',
}


@api_view(['POST'])
def upload_file(request):
    """
    Upload a single file (image or PDF). Requires authentication.
    POST: multipart/form-data with 'file' and optional 'upload_type' (logo, kyc_document, whatsapp_image).
    Returns: { url: "/media/...", path: "..." } (path relative to MEDIA_ROOT).
    """
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Not authenticated'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    upload_type = (request.POST.get('upload_type') or request.data.get('upload_type') or 'logo').strip().lower()
    if upload_type not in UPLOAD_SUBDIRS:
        upload_type = 'logo'

    subdir = UPLOAD_SUBDIRS[upload_type]
    # KYC allows PDF; logo and whatsapp_image are image only
    allow_pdf = upload_type == 'kyc_document'

    if 'file' not in request.FILES:
        return Response(
            {'error': 'No file provided. Use form field name "file".'},
            status=status.HTTP_400_BAD_REQUEST
        )

    uploaded = request.FILES['file']
    if uploaded.size > MAX_UPLOAD_SIZE:
        return Response(
            {'error': f'File too large. Maximum size is {MAX_UPLOAD_SIZE // (1024*1024)}MB.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    content_type = getattr(uploaded, 'content_type', '') or ''
    if content_type in ALLOWED_IMAGE_TYPES:
        pass
    elif allow_pdf and content_type == ALLOWED_PDF_TYPE:
        pass
    else:
        allowed = 'image (JPEG, PNG, GIF, WebP)' + (' or PDF' if allow_pdf else '')
        return Response(
            {'error': f'Invalid file type. Allowed: {allowed}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        ext = os.path.splitext(uploaded.name)[1] or ('.pdf' if content_type == ALLOWED_PDF_TYPE else '.jpg')
        if not ext.lower().startswith('.'):
            ext = '.' + ext
        safe_name = f"{uuid.uuid4().hex}{ext}"
        relative_path = os.path.join(subdir, safe_name)
        full_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as dest:
            for chunk in uploaded.chunks():
                dest.write(chunk)
        # URL as returned to client (MEDIA_URL is e.g. /media/)
        url = (settings.MEDIA_URL or '/media/').rstrip('/') + '/' + relative_path.replace('\\', '/')
        return Response({'url': url, 'path': relative_path}, status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.exception('upload_file error: %s', e)
        return Response(
            {'error': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
