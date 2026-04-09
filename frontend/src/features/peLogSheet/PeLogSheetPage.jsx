import React, { useCallback, useRef, useState } from 'react';
import { Workbook } from '@fortune-sheet/react';
import '@fortune-sheet/react/dist/index.css';
import SheetHeader from './components/SheetHeader';
import HelpModal from './components/HelpModal';
import ConflictBanner from './components/ConflictBanner';
import ConflictResolutionModal from './components/ConflictResolutionModal';
import { usePeLogSheet } from './hooks/usePeLogSheet';

export default function PeLogSheetPage() {
  const workbookRef = useRef(null);
  const [showHelp, setShowHelp] = useState(false);

  const {
    workbookData,
    revision,
    syncStatus,
    activeUsers,
    conflictMessage,
    conflictState,
    dismissConflict,
    keepServerConflictResolution,
    retryClientConflictValue,
    handleChange,
    handleOp,
    uploadCsv,
    downloadCsv,
  } = usePeLogSheet(workbookRef);

  const onOp = useCallback((ops) => {
    handleOp(ops);
  }, [handleOp]);

  if (!workbookData) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-teal-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-gray-500">PE Log Sheet 불러오는 중…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-white overflow-hidden">
        <SheetHeader
          syncStatus={syncStatus}
          revision={revision}
          activeUsers={activeUsers}
          onHelpOpen={() => setShowHelp(true)}
          onCsvUpload={uploadCsv}
          onCsvDownload={downloadCsv}
      />

      {conflictMessage && (
        <div className="px-4 pt-2">
          <ConflictBanner message={conflictMessage} onDismiss={dismissConflict} />
        </div>
      )}

      <div className="flex-1 overflow-hidden">
        <Workbook
          ref={workbookRef}
          data={workbookData}
          showToolbar={true}
          showFormulaBar={true}
          showSheetTabs={false}
          allowEdit={true}
          onChange={handleChange}
          onOp={onOp}
        />
      </div>

      {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}
      <ConflictResolutionModal
        conflictState={conflictState}
        onClose={dismissConflict}
        onKeepServer={keepServerConflictResolution}
        onRetryClientValue={retryClientConflictValue}
      />
    </div>
  );
}
