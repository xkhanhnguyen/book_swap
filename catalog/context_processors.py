def notification_count(request):
    if request.user.is_authenticated:
        try:
            count = request.user.notifications.filter(read=False).count()
        except Exception:
            count = 0
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}


def pending_swaps_count(request):
    if request.user.is_authenticated:
        try:
            from catalog.models import SwapRequest
            count = SwapRequest.objects.filter(
                book_instance__user=request.user,
                status='pending'
            ).count()
        except Exception:
            count = 0
        return {'pending_swaps_count': count}
    return {'pending_swaps_count': 0}
