from django.db import models
from django.contrib.auth.models import User
from PIL import Image


class Profile(models.Model):
    DISPLAY_PREF_CHOICES = [
        ('bookswap_id', 'BookSwap ID (anonymous)'),
        ('real_name',   'Real Name'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    avatar = models.ImageField(default='profile_images/default.jpg', upload_to='profile_images')
    bio = models.TextField(blank=True, default='')

    # address is transient — cleared after encryption; stored encrypted in address_encrypted
    address = models.TextField(blank=True, default='',
                               help_text='Private — only used to calculate distance, never shown to others')
    address_encrypted = models.TextField(blank=True, default='',
                                         help_text='AES-256-GCM encrypted address')
    city = models.CharField(max_length=200, blank=True, default='',
                            help_text='Shown publicly as your general location')
    latitude  = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    credit_balance = models.IntegerField(default=3)

    display_preference = models.CharField(
        max_length=20,
        choices=DISPLAY_PREF_CHOICES,
        default='bookswap_id',
    )

    # Feature 3: zip code for geocoding
    zip_code = models.CharField(max_length=20, blank=True, default='')

    # Feature 5: Verified Shipper Badge
    completed_swaps_count = models.IntegerField(default=0)
    is_verified_shipper   = models.BooleanField(default=False)

    # Feature 8: Email notifications
    email_notifications = models.BooleanField(default=True)

    @property
    def display_name(self) -> str:
        if self.display_preference == 'real_name':
            return self.user.get_full_name() or self.user.username
        return f'BookSwap #{self.user.id:04d}'

    @property
    def anonymous_id(self) -> str:
        return self.display_name

    # ─── Feature 4: Rating properties ────────────────────────────────────────

    @property
    def avg_rating(self):
        from catalog.models import SwapRating
        ratings = SwapRating.objects.filter(rated_user=self.user)
        if not ratings.exists():
            return None
        return round(ratings.aggregate(avg=models.Avg('score'))['avg'], 1)

    @property
    def total_ratings(self):
        from catalog.models import SwapRating
        return SwapRating.objects.filter(rated_user=self.user).count()

    @property
    def has_warning_badge(self):
        tr = self.total_ratings
        ar = self.avg_rating
        return tr >= 5 and ar is not None and ar < 2.0

    def stars_display(self):
        avg = self.avg_rating
        if avg is None:
            return ''
        full = int(avg)
        return '★' * full + '☆' * (5 - full)

    def __str__(self):
        return self.user.username

    def geocode(self):
        query = self.address.strip() or self.city.strip()
        if not query:
            # Feature 3: fall back to zip_code if no address/city
            if self.zip_code.strip():
                self._geocode_zip()
            return
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="bookswap_app")
            location = geolocator.geocode(query, timeout=5)
            if location:
                self.latitude  = location.latitude
                self.longitude = location.longitude
        except Exception:
            pass

    def _geocode_zip(self):
        """Feature 3: geocode using zip_code via pgeocode."""
        try:
            import pgeocode
            nomi = pgeocode.Nominatim(country='VN')
            result = nomi.query_postal_code(self.zip_code.strip())
            if result is not None and not (result['latitude'] != result['latitude']):  # NaN check
                lat = float(result['latitude'])
                lng = float(result['longitude'])
                if lat and lng:
                    self.latitude = lat
                    self.longitude = lng
        except Exception:
            pass

    def save(self, *args, **kwargs):
        old_zip = ''
        if self.pk:
            try:
                old = Profile.objects.get(pk=self.pk)
                old_zip = old.zip_code
                if self.address.strip() or old.city != self.city:
                    self.geocode()
                elif self.zip_code.strip() and self.zip_code != old_zip and not (self.latitude and self.longitude):
                    self._geocode_zip()
            except Profile.DoesNotExist:
                self.geocode()
        else:
            self.geocode()

        if self.address.strip():
            from catalog.utils.encryption import encrypt_address
            self.address_encrypted = encrypt_address(self.address)
            self.address = ''

        super().save(*args, **kwargs)

        try:
            img = Image.open(self.avatar.path)
            if img.height > 100 or img.width > 100:
                img.thumbnail((100, 100))
                img.save(self.avatar.path)
        except Exception:
            pass
