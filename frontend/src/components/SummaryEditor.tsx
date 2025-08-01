import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Save, X, Edit2 } from 'lucide-react';

interface SummaryEditorProps {
  nodeId: string;
  nodeName: string;
  initialSummary: string;
  onSave: (summary: string) => Promise<void>;
  onCancel: () => void;
}

export const SummaryEditor: React.FC<SummaryEditorProps> = ({
  nodeId,
  nodeName,
  initialSummary,
  onSave,
  onCancel
}) => {
  const [summary, setSummary] = useState(initialSummary);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const maxLength = 5000;

  useEffect(() => {
    setSummary(initialSummary);
    setError(null);
  }, [initialSummary]);

  const handleSave = async () => {
    if (summary.length > maxLength) {
      setError(`Summary must be ${maxLength} characters or less`);
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      await onSave(summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save summary');
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setSummary(initialSummary);
    setError(null);
    onCancel();
  };

  const hasChanges = summary !== initialSummary;
  const charCount = summary.length;
  const isOverLimit = charCount > maxLength;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="summary-editor" className="text-sm font-medium">
          Edit Summary for {nodeName}
        </Label>
        <div className="relative">
          <Textarea
            id="summary-editor"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Enter a summary for this entity..."
            className={`min-h-[150px] resize-y ${isOverLimit ? 'border-red-500' : ''}`}
            disabled={isSaving}
          />
          <div className={`absolute bottom-2 right-2 text-xs ${
            isOverLimit ? 'text-red-500' : 'text-muted-foreground'
          }`}>
            {charCount} / {maxLength}
          </div>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex gap-2 justify-end">
        <Button
          variant="outline"
          size="sm"
          onClick={handleCancel}
          disabled={isSaving}
        >
          <X className="h-4 w-4 mr-1" />
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={isSaving || !hasChanges || isOverLimit}
        >
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <Save className="h-4 w-4 mr-1" />
              Save
            </>
          )}
        </Button>
      </div>
    </div>
  );
};

// Inline edit button component
export const SummaryEditButton: React.FC<{ onClick: () => void }> = ({ onClick }) => {
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={onClick}
      className="h-8 px-2"
      title="Edit summary"
    >
      <Edit2 className="h-4 w-4" />
    </Button>
  );
};