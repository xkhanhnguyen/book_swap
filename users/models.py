from django.db import models
from django.contrib.auth.models import User
from PIL import Image


# Extending User Model Using a One-To-One Link
class Profile(models.Model):
    DISPLAY_PREF_CHOICES = [
        ('bookswap_id', 'BookSwap ID (anonymous)'),
        ('real_name',   'Real Name'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)

    avatar = models.ImageField(default='profile_images/default.jpg', upload_to='profile_images')
    bio = models.TextField(blank=True, default='')

    # address is transient — cleared after encryption; stored encrypted in address_encrypted
    address = models.TextField(blank=True, default='', help_text='Private — only used to calculate distance, never shown to others')
    address_encrypted = models.TextField(blank=True, default='', help_text='AES-256-GCM encrypted address')
    city = models.CharField(max_length=200, blank=True, default='', help_text='Shown publicly as your general location')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    points = models.IntegerField(default=20)
    credit_balance = models.IntegerField(default=0)

    display_preference = models.CharField(
        max_length=20,
        choices=DISPLAY_PREF_CHOICES,
        default='bookswap_id',
    )

    @property
    def display_name(self) -> str:
        """Public display name based on the user's preference."""
        if self.display_preference == 'real_name':
            return self.user.get_full_name() or self.user.username
        return f'BookSwap #{self.user.id:04d}'

    @property
    def anonymous_id(self) -> str:
        """Legacy alias — use display_name instead."""
        return self.display_name

    def __str__(self):
        return self.user.username

    def geocode(self):
        """Geocode address (private) or fall back to city for lat/lng."""
        query = self.address.strip() or self.city.strip()
        if not query:
            return
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="bookswap_app")
            location = geolocator.geocode(query, timeout=5)
            if location:
                self.latitude = location.latitude
                self.longitude = location.longitude
        except Exception:
            pass

    def save(self, *args, **kwargs):
        # Geocode when address or city changes
        if self.pk:
            try:
                old = Profile.objects.get(pk=self.pk)
                if self.address.strip() or old.city != self.city:
                    self.geocode()
            except Profile.DoesNotExist:
                self.geocode()
        else:
            self.geocode()

        # Encrypt plaintext address then clear it from DB
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
