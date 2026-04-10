"""
Nearby books helper for the analytics dashboard.

get_nearby_books(user, radius_miles=50)
    Returns a list of {'copy': BookInstance, 'distance_miles': float} for all
    available BookInstances within *radius_miles* of *user*.

    Returns None  — user has no location data (can't calculate distance).
    Returns []    — user has a location but nothing is within range.

ZipCodeCache is used to avoid repeated Nominatim geocode calls for owner
profiles that have a zip code but no lat/lon stored yet.
"""

import logging

from geopy.distance import geodesic

logger = logging.getLogger(__name__)


def _get_cached_coords(zip_code):
    """
    Return (latitude, longitude) for *zip_code*, using ZipCodeCache.
    Geocodes via Nominatim on a cache miss and stores the result.
    Returns (None, None) on any failure.
    """
    if not zip_code or not zip_code.strip():
        return None, None

    import datetime
    from django.conf import settings
    from django.utils import timezone
    from catalog.models import ZipCodeCache

    expiry_days = getattr(settings, 'ZIP_CACHE_EXPIRY_DAYS', 30)
    threshold = timezone.now() - datetime.timedelta(days=expiry_days)

    cached = ZipCodeCache.objects.filter(
        zip_code=zip_code, cached_at__gte=threshold
    ).first()
    if cached:
        return cached.latitude, cached.longitude

    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent='bookswap_analytics', timeout=5)
        location = geolocator.geocode(zip_code.strip())
        if location:
            ZipCodeCache.objects.update_or_create(
                zip_code=zip_code,
                defaults={
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                },
            )
            return location.latitude, location.longitude
    except Exception as exc:
        logger.debug('Could not geocode zip %s: %s', zip_code, exc)

    return None, None


def get_nearby_books(user, radius_miles=50):
    """
    Return available BookInstances within *radius_miles* of *user*.

    Strategy (avoids N+1):
    1. Bulk-fetch all available copies with select_related (single JOIN query).
    2. Collect zip codes whose profiles have no lat/lon.
    3. Geocode those zip codes in one pass (cached).
    4. Filter entirely in Python — no extra DB round-trips.
    """
    try:
        user_lat = user.profile.latitude
        user_lon = user.profile.longitude
        if not user_lat or not user_lon:
            return None

        from catalog.models import BookInstance

        copies = (
            BookInstance.objects
            .filter(status='a')
            .exclude(user=user)
            .select_related('user__profile', 'book__author')
            .prefetch_related('book__genre')
        )

        # Collect zip codes that need geocoding (profile has no lat/lon)
        zips_needed = set()
        for copy in copies:
            try:
                p = copy.user.profile
                if (p.latitude is None or p.longitude is None) and p.zip_code:
                    zips_needed.add(p.zip_code)
            except Exception:
                pass

        # Geocode in bulk (one Nominatim call per unique uncached zip)
        zip_coords = {zc: _get_cached_coords(zc) for zc in zips_needed}

        user_point = (user_lat, user_lon)
        nearby = []
        for copy in copies:
            try:
                p = copy.user.profile
                lat, lon = p.latitude, p.longitude
                if (lat is None or lon is None) and p.zip_code:
                    lat, lon = zip_coords.get(p.zip_code, (None, None))
                if lat is None or lon is None:
                    continue
                dist = geodesic(user_point, (lat, lon)).miles
                if dist <= radius_miles:
                    nearby.append({'copy': copy, 'distance_miles': round(dist, 1)})
            except Exception:
                continue

        return nearby

    except Exception as exc:
        logger.warning('get_nearby_books failed: %s', exc)
        return None
