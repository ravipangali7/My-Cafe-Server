"""
WhatsApp Notification views: list (view-only), detail (for progress), create (with background send).
"""
import json
import logging
import os
import threading
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction

from ..models import WhatsAppNotification, VendorCustomer, User
from ..serializers import WhatsAppNotificationSerializer, WhatsAppNotificationListSerializer
from ..services.whatsapp_service import send_marketing_whatsapp

logger = logging.getLogger(__name__)


def _get_queryset(request):
    """Vendor sees own notifications; superuser sees all (optional user_id filter)."""
    if request.user.is_superuser:
        qs = WhatsAppNotification.objects.all()
        user_id = request.GET.get('user_id')
        if user_id:
            try:
                qs = qs.filter(user_id=int(user_id))
            except ValueError:
                pass
    else:
        qs = WhatsAppNotification.objects.filter(user=request.user)
    return qs.select_related('user').prefetch_related('customers').order_by('-created_at')


@api_view(['GET'])
def whatsapp_notification_list(request):
    """List WhatsApp notifications. Vendors see own; superuser sees all. Read-only."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        search = request.GET.get('search', '').strip()
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 10)), 100)
        queryset = _get_queryset(request)
        if search:
            queryset = queryset.filter(message__icontains=search)
        paginator = Paginator(queryset, page_size)
        total_pages = paginator.num_pages
        if page > total_pages and total_pages > 0:
            page = total_pages
        if page < 1:
            page = 1
        page_obj = paginator.get_page(page)
        serializer = WhatsAppNotificationListSerializer(
            page_obj.object_list, many=True, context={'request': request}
        )
        return Response({
            'data': serializer.data,
            'count': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        }, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception('whatsapp_notification_list error')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def whatsapp_notification_detail(request, id):
    """Get one WhatsApp notification (for progress polling and view)."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        notification = WhatsAppNotification.objects.filter(pk=id).select_related('user').prefetch_related('customers').first()
        if not notification:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        if not request.user.is_superuser and notification.user_id != request.user.id:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        serializer = WhatsAppNotificationSerializer(notification, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        logger.exception('whatsapp_notification_detail error')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _run_send_marketing(notification_id):
    """Background thread: load notification and run send_marketing_whatsapp."""
    try:
        notification = WhatsAppNotification.objects.filter(pk=notification_id).select_related('user').prefetch_related('customers').first()
        if notification:
            send_marketing_whatsapp(notification)
    except Exception as e:
        logger.exception('Background send_marketing_whatsapp failed for notification %s', notification_id)
        try:
            WhatsAppNotification.objects.filter(pk=notification_id).update(
                status=WhatsAppNotification.STATUS_FAILED
            )
        except Exception:
            pass


@api_view(['POST'])
def whatsapp_notification_create(request):
    """Create a WhatsApp notification and start sending in background. Returns notification id."""
    if not request.user.is_authenticated:
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        # Parse body: multipart (image) or JSON
        data = request.data if hasattr(request, 'data') and request.data is not None else {}
        if not data and request.body:
            try:
                data = json.loads(request.body.decode('utf-8'))
            except (ValueError, TypeError):
                data = {}
        # Form/multipart may have message in POST
        if not data and hasattr(request, 'POST'):
            data = dict(request.POST) if request.POST else {}
            for k, v in list(data.items()):
                if isinstance(v, (list, tuple)) and len(v) == 1:
                    data[k] = v[0]
        message = (data.get('message') or '').strip() if isinstance(data.get('message'), str) else ''
        if not message:
            return Response({'error': 'message is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve customer set: vendor is request.user (or superuser acting as vendor via user_id)
        vendor = request.user
        if request.user.is_superuser:
            uid = data.get('user_id')
            if uid is not None:
                try:
                    vendor = User.objects.get(pk=int(uid), is_superuser=False)
                except (User.DoesNotExist, ValueError):
                    return Response({'error': 'Invalid user_id'}, status=status.HTTP_400_BAD_REQUEST)
        select_all = data.get('select_all') in (True, 'true', '1', 'yes')
        customer_ids = data.get('customer_ids')
        if isinstance(customer_ids, str):
            try:
                customer_ids = json.loads(customer_ids)
            except (ValueError, TypeError):
                customer_ids = None
        if not select_all and not customer_ids:
            return Response({'error': 'Either select_all or customer_ids is required'}, status=status.HTTP_400_BAD_REQUEST)

        if select_all:
            customer_ids = list(VendorCustomer.objects.filter(user=vendor).values_list('id', flat=True))
        else:
            if not isinstance(customer_ids, (list, tuple)):
                customer_ids = []
            try:
                customer_ids = [int(x) for x in customer_ids]
            except (ValueError, TypeError):
                return Response({'error': 'customer_ids must be a list of integers'}, status=status.HTTP_400_BAD_REQUEST)
            # Ensure all customers belong to this vendor
            valid_ids = set(
                VendorCustomer.objects.filter(user=vendor, id__in=customer_ids).values_list('id', flat=True)
            )
            customer_ids = [i for i in customer_ids if i in valid_ids]
        if not customer_ids:
            return Response({'error': 'No valid customers selected'}, status=status.HTTP_400_BAD_REQUEST)

        # Image: from multipart or image_url (WebView upload)
        image_file = request.FILES.get('image') if request.FILES else None
        image_url = (data.get('image_url') or '').strip()

        with transaction.atomic():
            notification = WhatsAppNotification.objects.create(
                message=message.strip(),
                user=vendor,
                status=WhatsAppNotification.STATUS_SENDING,
                total_count=len(customer_ids),
                sent_count=0,
            )
            if image_file:
                notification.image = image_file
                notification.save(update_fields=['image'])
            elif image_url:
                media_url = (getattr(settings, 'MEDIA_URL') or '/media/').rstrip('/')
                if image_url.startswith(media_url + '/') or image_url.startswith(media_url):
                    rel = image_url.replace(media_url, '').lstrip('/')
                    full_path = os.path.join(settings.MEDIA_ROOT, rel)
                    if os.path.isfile(full_path):
                        with open(full_path, 'rb') as f:
                            notification.image.save(os.path.basename(rel), ContentFile(f.read()), save=True)
            notification.customers.set(customer_ids)

        # Start background send
        thread = threading.Thread(target=_run_send_marketing, args=(notification.id,), daemon=True)
        thread.start()

        return Response(
            {'id': notification.id, 'status': notification.status, 'total_count': notification.total_count},
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        logger.exception('whatsapp_notification_create error')
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
