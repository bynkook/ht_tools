from django.db import models
from django.contrib.auth.models import User


class DataExplorerPreset(models.Model):
    """
    Stores a saved visualization preset for Data Explorer.
    Includes data loading configuration and Graphic Walker chart specification.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='data_explorer_presets',
        help_text="Owner of this preset"
    )
    name = models.CharField(
        max_length=200,
        help_text="Display name for the preset"
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Optional description of the visualization"
    )
    
    # Data loading configuration
    # Stores: { filename: str, selectedColumns: [{name, semantic_type, include}] }
    data_config = models.JSONField(
        help_text="Data loading configuration (filename, selected columns)"
    )
    
    # Graphic Walker chart specification (IChart interface)
    # Stores: { visId, name, encodings, config, layout }
    chart_spec = models.JSONField(
        help_text="Graphic Walker IChart specification"
    )
    
    # Field metadata for restoration (IMutField[])
    # Stores: [{ fid, name, semanticType, analyticType, ... }]
    fields_meta = models.JSONField(
        help_text="Field metadata for schema reconstruction"
    )
    
    # Public visibility flag
    # If True, all users can see this preset; if False, only the owner can see it
    is_public = models.BooleanField(
        default=False,
        help_text="If True, this preset is visible to all users"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    
    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_public', '-updated_at']),
        ]
        verbose_name = "Data Explorer Preset"
        verbose_name_plural = "Data Explorer Presets"
    
    def __str__(self):
        return f"{self.name} ({self.user.username})"
