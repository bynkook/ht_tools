from django.urls import path
from .views import (
    SheetCellLockAcquireView,
    SheetCellLockHeartbeatView,
    SheetCellLockReleaseView,
    SheetCsvDownloadView,
    SheetCsvUploadView,
    SheetOpsView,
    SheetPresenceHeartbeatView,
    SheetPresenceJoinView,
    SheetPresenceLeaveView,
    SheetResetView,
    SheetStateView,
    SheetStreamSseView,
)

urlpatterns = [
    path("state/", SheetStateView.as_view(), name="pe-log-state"),
    path("ops/", SheetOpsView.as_view(), name="pe-log-ops"),
    path("stream/", SheetStreamSseView.as_view(), name="pe-log-stream"),
    path(
        "presence/join/", SheetPresenceJoinView.as_view(), name="pe-log-presence-join"
    ),
    path(
        "presence/heartbeat/",
        SheetPresenceHeartbeatView.as_view(),
        name="pe-log-presence-heartbeat",
    ),
    path(
        "presence/leave/",
        SheetPresenceLeaveView.as_view(),
        name="pe-log-presence-leave",
    ),
    path(
        "cell-lock/acquire/",
        SheetCellLockAcquireView.as_view(),
        name="pe-log-cell-lock-acquire",
    ),
    path(
        "cell-lock/heartbeat/",
        SheetCellLockHeartbeatView.as_view(),
        name="pe-log-cell-lock-heartbeat",
    ),
    path(
        "cell-lock/release/",
        SheetCellLockReleaseView.as_view(),
        name="pe-log-cell-lock-release",
    ),
    path("csv-upload/", SheetCsvUploadView.as_view(), name="pe-log-csv-upload"),
    path("csv-download/", SheetCsvDownloadView.as_view(), name="pe-log-csv-download"),
    path("reset-from-source/", SheetResetView.as_view(), name="pe-log-reset"),
]
