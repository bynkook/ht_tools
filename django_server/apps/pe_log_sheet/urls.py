from django.urls import path
from .views import (
    SheetCsvDownloadView,
    SheetCsvUploadView,
    SheetOpsView,
    SheetResetView,
    SheetStateView,
    SheetStreamView,
)

urlpatterns = [
    path('state/', SheetStateView.as_view(), name='pe-log-state'),
    path('ops/', SheetOpsView.as_view(), name='pe-log-ops'),
    path('stream/', SheetStreamView.as_view(), name='pe-log-stream'),
    path('csv-upload/', SheetCsvUploadView.as_view(), name='pe-log-csv-upload'),
    path('csv-download/', SheetCsvDownloadView.as_view(), name='pe-log-csv-download'),
    path('reset-from-source/', SheetResetView.as_view(), name='pe-log-reset'),
]
