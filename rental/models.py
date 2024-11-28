from django.db import models
import bnbu_constants.constants as constants


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RentalProperty(BaseModel):
    no_of_bedrooms = models.IntegerField(null=True, blank=True)
    no_of_bathrooms = models.IntegerField(null=True, blank=True)
    square_feet = models.IntegerField(null=True, blank=True)
    rent = models.IntegerField(null=True, blank=True)
    property_zillow_link = models.URLField()
    location = models.CharField(max_length=255, blank=True, null=True)
    property_status = models.CharField(max_length=20, choices=constants.RENTAL_PROPERY_STATUS_CHOICES,
                                       default=constants.PENDING)

    # Will be extracted from AIR DNA API
    yearly_projected_revenue = models.IntegerField(null=True, blank=True)
    monthly_estimated_profit = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    batch_id = models.IntegerField()

    def __str__(self):
        return self.location

    class Meta:
        verbose_name = "Rental Property"
        verbose_name_plural = "Rental Properties"
