from django.db import models

# Create your models here.
from django.db import models

class Factory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Factories"

    def __str__(self):
        return self.name

class ProductionLine(models.Model):
    factory = models.ForeignKey(Factory, on_delete=models.CASCADE, relatives="lines")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('factory', 'name')

    def __str__(self):
        return f"{self.factory.name} - {self.name}"
