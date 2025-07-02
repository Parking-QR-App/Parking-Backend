# # alert_service/models/parking_alert.py
# from django.db import models
# from django.conf import settings

# class ParkingAlert(models.Model):
#     reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
#     license_plate = models.CharField(max_length=20)
#     photo_url = models.URLField(max_length=500, blank=True)
#     location = models.JSONField()
#     created_at = models.DateTimeField(auto_now_add=True)

#     def create_notification(self):
#         from .notification import Notification
#         return Notification.objects.create(
#             user=self.reporter,
#             type=Notification.Type.PARKING_ALERT,
#             title="Parking Violation Reported",
#             message=f"License plate: {self.license_plate}",
#             metadata={
#                 "alert_id": str(self.id),
#                 "location": self.location
#             }
#         )