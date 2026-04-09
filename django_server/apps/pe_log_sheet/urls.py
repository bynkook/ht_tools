from django.urls import path
from .views import SheetStateView, SheetOpsView, SheetStreamView, SheetResetView

urlpatterns = [
    path('state/', SheetStateView.as_view(), name='pe-log-state'),
    path('ops/', SheetOpsView.as_view(), name='pe-log-ops'),
    path('stream/', SheetStreamView.as_view(), name='pe-log-stream'),
    path('reset-from-source/', SheetResetView.as_view(), name='pe-log-reset'),
]
