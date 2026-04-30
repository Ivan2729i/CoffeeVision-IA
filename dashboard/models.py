from django.db import models
from django.db.models import Q
from decimal import Decimal
from django.core.validators import MinValueValidator
from django.conf import settings


class Provider(models.Model):
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=120)
    contact = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


class Batch(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_EVALUATED = "evaluated"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Borrador"),
        (STATUS_EVALUATED, "Evaluado"),
    ]

    code = models.CharField(
        max_length=12,
        unique=True,
        db_index=True,
        editable=False,
    )
    provider = models.ForeignKey(
        Provider,
        on_delete=models.PROTECT,
        related_name="batches",
    )
    weight_kg = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    class Meta:
        verbose_name = "Lote"
        verbose_name_plural = "Lotes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.code

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if creating and not self.code:
            self.code = self._generate_next_code()

        super().save(*args, **kwargs)

        if hasattr(self, "evaluation") and self.status != self.STATUS_EVALUATED:
            Batch.objects.filter(pk=self.pk).update(status=self.STATUS_EVALUATED)

    @staticmethod
    def _generate_next_code() -> str:
        last = Batch.objects.order_by("-id").first()
        next_num = (last.id + 1) if last else 1
        return f"L-{next_num:04d}"

    @property
    def is_evaluated(self) -> bool:
        return hasattr(self, "evaluation")

    @property
    def packing_status(self) -> str | None:
        if hasattr(self, "packing"):
            return self.packing.status
        return None


class Evaluation(models.Model):
    METHOD_IMAGE = "image"
    METHOD_CAMERA = "camera"
    METHOD_CHOICES = [
        (METHOD_IMAGE, "Imagen"),
        (METHOD_CAMERA, "Cámara"),
    ]

    batch = models.OneToOneField(
        Batch,
        on_delete=models.CASCADE,
        related_name="evaluation",
    )

    method = models.CharField(max_length=16, choices=METHOD_CHOICES, default=METHOD_IMAGE)

    # Grado 1-4
    grade = models.PositiveSmallIntegerField(null=True, blank=True)

    # Puntaje
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Totales
    primary_total = models.PositiveIntegerField(default=0)
    secondary_total = models.PositiveIntegerField(default=0)
    defects_total = models.PositiveIntegerField(default=0)

    counts = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evaluación"
        verbose_name_plural = "Evaluaciones"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(grade__isnull=True) | Q(grade__gte=1, grade__lte=4),
                name="evaluation_grade_between_1_and_4_or_null",
            )
        ]

    def __str__(self) -> str:
        return f"Evaluación {self.batch.code}"

    def recompute_totals_from_counts(self):
        data = self.counts or {}
        p = data.get("primary", {}) or {}
        s = data.get("secondary", {}) or {}

        primary_total = 0
        for v in p.values():
            if v is None:
                continue
            primary_total += int(v)

        secondary_total = 0
        for v in s.values():
            if v is None:
                continue
            secondary_total += int(v)

        self.primary_total = primary_total
        self.secondary_total = secondary_total
        self.defects_total = primary_total + secondary_total

    def save(self, *args, **kwargs):
        self.recompute_totals_from_counts()

        super().save(*args, **kwargs)

        Batch.objects.filter(pk=self.batch_id).update(status=Batch.STATUS_EVALUATED)

        # Crear packing automático al evaluar el lote
        Packing.objects.get_or_create(batch=self.batch)


class Packing(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PACKED = "packed"
    STATUS_SENT = "sent"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pendiente"),
        (STATUS_PACKED, "Empacado"),
        (STATUS_SENT, "Enviado"),
    ]

    batch = models.OneToOneField(
        Batch,
        on_delete=models.CASCADE,
        related_name="packing",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    packed_at = models.DateField(null=True, blank=True)
    sent_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Packing"
        verbose_name_plural = "Packing"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"Packing {self.batch.code}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not hasattr(self.batch, "evaluation"):
            raise ValidationError("Solo se puede crear packing para lotes evaluados.")

        if self.status == self.STATUS_PENDING:
            self.packed_at = None
            self.sent_at = None

        if self.status == self.STATUS_PACKED:
            if not self.packed_at:
                raise ValidationError("La fecha de empaque es obligatoria cuando el estado es Empacado.")
            self.sent_at = None

        if self.status == self.STATUS_SENT:
            if not self.packed_at:
                raise ValidationError("Para marcar como Enviado, primero debe existir fecha de empaque.")
            if not self.sent_at:
                raise ValidationError("La fecha de envío es obligatoria cuando el estado es Enviado.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class ActivityLog(models.Model):
    LEVEL_INFO = "info"
    LEVEL_SUCCESS = "success"
    LEVEL_WARNING = "warning"
    LEVEL_ERROR = "error"
    LEVEL_CHOICES = [
        (LEVEL_INFO, "Info"),
        (LEVEL_SUCCESS, "Success"),
        (LEVEL_WARNING, "Warning"),
        (LEVEL_ERROR, "Error"),
    ]

    MODULE_AUTH = "auth"
    MODULE_QUALITY = "quality"
    MODULE_PACKAGING = "packaging"
    MODULE_REPORTS = "reports"
    MODULE_SETTINGS = "settings"
    MODULE_CHOICES = [
        (MODULE_AUTH, "Auth"),
        (MODULE_QUALITY, "Quality"),
        (MODULE_PACKAGING, "Packaging"),
        (MODULE_REPORTS, "Reports"),
        (MODULE_SETTINGS, "Settings"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    module = models.CharField(max_length=20, choices=MODULE_CHOICES)
    action = models.CharField(max_length=100)
    description = models.TextField()
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default=LEVEL_INFO)

    object_type = models.CharField(max_length=50, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    object_label = models.CharField(max_length=120, blank=True, null=True)

    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.module}] {self.description}"


class Alert(models.Model):
    SEVERITY_WARNING = "warning"
    SEVERITY_ERROR = "error"
    SEVERITY_CRITICAL = "critical"
    SEVERITY_CHOICES = [
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_ERROR, "Error"),
        (SEVERITY_CRITICAL, "Critical"),
    ]

    CATEGORY_QUALITY = "quality"
    CATEGORY_EVALUATION = "evaluation"
    CATEGORY_CAMERA = "camera"
    CATEGORY_REPORT = "report"
    CATEGORY_SYSTEM = "system"
    CATEGORY_CHOICES = [
        (CATEGORY_QUALITY, "Quality"),
        (CATEGORY_EVALUATION, "Evaluation"),
        (CATEGORY_CAMERA, "Camera"),
        (CATEGORY_REPORT, "Report"),
        (CATEGORY_SYSTEM, "System"),
    ]

    title = models.CharField(max_length=150)
    message = models.TextField()

    severity = models.CharField(
        max_length=10,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_WARNING,
        db_index=True,
    )

    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_SYSTEM,
        db_index=True,
    )

    batch = models.ForeignKey(
        Batch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )

    evaluation = models.ForeignKey(
        Evaluation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_alerts",
    )

    is_active = models.BooleanField(default=True, db_index=True)
    is_seen = models.BooleanField(default=False, db_index=True)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"
        ordering = ["is_seen", "-created_at"]

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"


class DefectCatalog(models.Model):
    TYPE_PRIMARY = "primary"
    TYPE_SECONDARY = "secondary"

    TYPE_CHOICES = [
        (TYPE_PRIMARY, "Primario"),
        (TYPE_SECONDARY, "Secundario"),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    defect_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    equivalence = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = "Catálogo de defecto"
        verbose_name_plural = "Catálogo de defectos"
        ordering = ["defect_type", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class QualitySettings(models.Model):
    sample_size_grams = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("350.00"),
        validators=[MinValueValidator(Decimal("100.00"))],
    )

    class Meta:
        verbose_name = "Configuración de calidad"
        verbose_name_plural = "Configuración de calidad"

    def __str__(self):
        return f"Muestra: {self.sample_size_grams} g"

    @classmethod
    def get_current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class EvaluationDefect(models.Model):
    evaluation = models.ForeignKey(
        Evaluation,
        on_delete=models.CASCADE,
        related_name="defect_results",
    )

    defect = models.ForeignKey(
        DefectCatalog,
        on_delete=models.PROTECT,
        related_name="evaluation_results",
    )

    raw_count = models.PositiveIntegerField(default=0)
    official_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Defecto detectado en evaluación"
        verbose_name_plural = "Defectos detectados en evaluaciones"
        unique_together = ("evaluation", "defect")

    def __str__(self):
        return f"{self.evaluation.batch.code} - {self.defect.code}"

