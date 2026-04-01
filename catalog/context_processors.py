def notification_count(request):
    if request.user.is_authenticated:
        try:
            count = request.user.notifications.filter(read=False).count()
        except Exception:
            count = 0
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0}
