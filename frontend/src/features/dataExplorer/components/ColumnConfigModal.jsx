import React, { useState, useMemo } from 'react';
import { X, CheckSquare, Square, Table2 } from 'lucide-react';

/**
 * Semantic type options for Graphic Walker
 */
const TYPE_OPTIONS = [
  { value: 'quantitative', label: '숫자 (Quantitative)' },
  { value: 'temporal', label: '날짜/시간 (Temporal)' },
  { value: 'nominal', label: '범주형 (Nominal)' }
];

/**
 * Column Configuration Modal
 * 
 * Displays preview data and allows users to:
 * - Select which columns to include
 * - Set semantic type for each column
 * 
 * Note: Preview shows raw data as-is from CSV file.
 * Data transformation happens in DuckDB/Graphic Walker, not in preview.
 */
const ColumnConfigModal = ({
  isOpen,
  onClose,
  onConfirm,
  filename,
  previewData,
  detectedColumns
}) => {
  // Initialize column states from detected columns
  // Each column: { name, include, semanticType }
  const [columnStates, setColumnStates] = useState(() => {
    return detectedColumns.map(col => ({
      name: col.name,
      include: true, // Default: all columns selected
      semanticType: col.detected_type
    }));
  });

  // Reset states when modal opens with new data
  React.useEffect(() => {
    if (isOpen && detectedColumns.length > 0) {
      setColumnStates(
        detectedColumns.map(col => ({
          name: col.name,
          include: true,
          semanticType: col.detected_type
        }))
      );
    }
  }, [isOpen, detectedColumns]);

  // Count selected columns
  const selectedCount = useMemo(() => {
    return columnStates.filter(col => col.include).length;
  }, [columnStates]);

  // Toggle single column
  const toggleColumn = (index) => {
    setColumnStates(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], include: !updated[index].include };
      return updated;
    });
  };

  // Change column type
  const changeColumnType = (index, newType) => {
    setColumnStates(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], semanticType: newType };
      return updated;
    });
  };

  // Select all columns
  const selectAll = () => {
    setColumnStates(prev => prev.map(col => ({ ...col, include: true })));
  };

  // Deselect all columns
  const deselectAll = () => {
    setColumnStates(prev => prev.map(col => ({ ...col, include: false })));
  };

  // Handle confirm
  const handleConfirm = () => {
    // Convert to format expected by backend
    const columns = columnStates.map(col => ({
      name: col.name,
      semantic_type: col.semanticType,
      include: col.include
    }));
    onConfirm(columns);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-[90vw] max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <Table2 className="text-blue-600" size={20} />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-800">컬럼 설정</h2>
              <p className="text-sm text-gray-500">{filename}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Preview Section */}
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-700 mb-3">
            Data Preview (상위 10행)
          </h3>
          <div className="overflow-auto max-h-48 border border-gray-200 rounded-lg">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  {detectedColumns.map((col, idx) => (
                    <th 
                      key={idx}
                      className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap border-b border-gray-200"
                    >
                      {col.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewData.map((row, rowIdx) => (
                  <tr key={rowIdx} className="hover:bg-gray-50">
                    {detectedColumns.map((col, colIdx) => {
                      const rawValue = row[col.name];
                      const isNull = rawValue === null || rawValue === undefined;
                      
                      return (
                        <td 
                          key={colIdx}
                          className="px-3 py-1.5 text-gray-700 whitespace-nowrap border-b border-gray-100 max-w-[200px] truncate"
                          title={isNull ? '' : String(rawValue)}
                        >
                          {isNull 
                            ? <span className="text-gray-300 italic">null</span>
                            : String(rawValue)
                          }
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Column Selection Section */}
        <div className="flex-1 px-6 py-4 overflow-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-700">
              컬럼 선택 및 타입 설정
              <span className="ml-2 text-gray-400 font-normal">
                ({selectedCount}/{columnStates.length} 선택됨)
              </span>
            </h3>
            <div className="flex gap-2">
              <button
                onClick={selectAll}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors"
              >
                <CheckSquare size={14} />
                전체 선택
              </button>
              <button
                onClick={deselectAll}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              >
                <Square size={14} />
                전체 해제
              </button>
            </div>
          </div>

          {/* Column List */}
          <div className="space-y-1 max-h-72 overflow-auto">
            {columnStates.map((col, idx) => (
              <div 
                key={idx}
                className={`flex items-center gap-3 px-3 py-1.5 rounded-md border transition-colors ${
                  col.include 
                    ? 'bg-white border-blue-200' 
                    : 'bg-gray-50 border-gray-200 opacity-60'
                }`}
              >
                {/* Checkbox */}
                <button
                  onClick={() => toggleColumn(idx)}
                  className={`p-0.5 rounded ${col.include ? 'text-blue-600' : 'text-gray-400'}`}
                >
                  {col.include ? <CheckSquare size={16} /> : <Square size={16} />}
                </button>

                {/* Column Name */}
                <span className={`flex-1 text-xs font-medium ${col.include ? 'text-gray-800' : 'text-gray-500'}`}>
                  {col.name}
                </span>

                {/* Type Selector */}
                <select
                  value={col.semanticType}
                  onChange={(e) => changeColumnType(idx, e.target.value)}
                  disabled={!col.include}
                  className={`px-2 py-1 text-xs border rounded focus:outline-none focus:ring-1 focus:ring-blue-300 ${
                    col.include 
                      ? 'bg-white border-gray-300 text-gray-700' 
                      : 'bg-gray-100 border-gray-200 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {TYPE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={selectedCount === 0}
            className={`px-6 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
              selectedCount > 0 
                ? 'bg-blue-600 hover:bg-blue-700' 
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};

export default ColumnConfigModal;
