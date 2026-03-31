from django.db import models
from django.contrib.auth.models import User
from PIL import Image


# Extending User Model Using a One-To-One Link
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    avatar = models.ImageField(default='profile_images/default.jpg', upload_to='profile_images')
    bio = models.TextField(blank=True, default='')

    city = models.CharField(max_length=200, blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    points = models.IntegerField(default=20)

    def __str__(self):
        return self.user.username

    def geocode_city(self):
        """Convert city name to lat/lng using Nominatim."""
        if not self.city:
            return
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="bookswap_app")
            location = geolocator.geocode(self.city, timeout=5)
            if location:
                self.latitude = location.latitude
                self.longitude = location.longitude
        except Exception:
            pass

    def save(self, *args, **kwargs):
        # Geocode city if it changed
        if self.pk:
            try:
                old = Profile.objects.get(pk=self.pk)
                if old.city != self.city:
                    self.geocode_city()
            except Profile.DoesNotExist:
                self.geocode_city()
        else:
            self.geocode_city()

        super().save()

        try:
            img = Image.open(self.avatar.path)
            if img.height > 100 or img.width > 100:
                img.thumbnail((100, 100))
                img.save(self.avatar.path)
        except Exception:
            pass