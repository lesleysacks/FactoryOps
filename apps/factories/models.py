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
    factory = models.ForeignKey(Factory, on_delete=models.CASCADE, related_name="lines")
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('factory', 'name')

    def __str__(self):
        if self.code:
            return f"{self.factory.name} - {self.name} ({self.code})"
        return f"{self.factory.name} - {self.name}"
