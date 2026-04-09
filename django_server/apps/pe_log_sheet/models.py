from django.db import models
from django.contrib.auth.models import User


class PeLogSheetState(models.Model):
    """Shared authoritative snapshot of the PE log spreadsheet."""

    singleton_key = models.CharField(max_length=32, unique=True, default='main')
    workbook_data = models.JSONField(default=list)
    revision = models.BigIntegerField(default=0)
    source_checksum = models.CharField(max_length=64, blank=True, default='')
    last_editor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='pe_log_sheet_edits',
    )
    initialized_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'PE Log Sheet State'
        verbose_name_plural = 'PE Log Sheet States'

    def __str__(self):
        return f'PE Log Sheet (rev={self.revision})'


class PeLogSheetRevision(models.Model):
    """Append-only op log for auditing and conflict analysis."""

    document = models.ForeignKey(
        PeLogSheetState, on_delete=models.CASCADE, related_name='revisions',
    )
    base_revision = models.BigIntegerField()
    new_revision = models.BigIntegerField()
    ops = models.JSONField(default=list)
    editor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='pe_log_sheet_revisions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'PE Log Sheet Revision'
        verbose_name_plural = 'PE Log Sheet Revisions'

    def __str__(self):
        return f'Revision {self.base_revision} -> {self.new_revision}'
