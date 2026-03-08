import React, { useEffect } from 'react';
import { GraphicWalker } from '@kanaries/graphic-walker';

const DataExplorerChart = ({
  currentFile,
  fields,
  computation,
  storeRef,
  chartSpec,
  onError,
  onReadyChange,
}) => {
  useEffect(() => {
    onReadyChange?.(true);

    return () => {
      onReadyChange?.(false);
    };
  }, [onReadyChange]);

  return (
    <GraphicWalker
      key={currentFile}
      fields={fields}
      appearance="light"
      computation={computation}
      storeRef={storeRef}
      chart={chartSpec}
      i18nLang="en-US"
      hideDataSourceConfig={true}
      hideProfiling={true}
      experimentalFeatures={{ computedField: true }}
      onError={(err) => onError?.(err.message)}
    />
  );
};

export default DataExplorerChart;