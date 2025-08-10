import React from 'react';
import { Button } from './ui/button';
import { FlaskConical, FlaskConicalOff } from 'lucide-react';

export const RefactoredToggle: React.FC = () => {
  const [isRefactored, setIsRefactored] = React.useState(() => {
    return localStorage.getItem('graphiti.useRefactoredComponents') === 'true';
  });

  const handleToggle = () => {
    const newValue = !isRefactored;
    localStorage.setItem('graphiti.useRefactoredComponents', String(newValue));
    setIsRefactored(newValue);
    
    // Show message and reload after a short delay
    const message = newValue 
      ? 'Switching to refactored components...' 
      : 'Switching to original components...';
    
    console.log(`[RefactoredToggle] ${message}`);
    
    // Create a toast notification
    const toast = document.createElement('div');
    toast.className = 'fixed top-4 right-4 z-50 bg-primary text-primary-foreground px-4 py-2 rounded-lg shadow-lg';
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
      document.body.removeChild(toast);
      window.location.reload();
    }, 1000);
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handleToggle}
      className="flex items-center gap-2"
      title={isRefactored ? 'Using refactored components (click to switch to original)' : 'Using original components (click to switch to refactored)'}
    >
      {isRefactored ? (
        <>
          <FlaskConical className="h-4 w-4 text-green-500" />
          <span className="text-xs text-green-500">Refactored</span>
        </>
      ) : (
        <>
          <FlaskConicalOff className="h-4 w-4 text-muted-foreground" />
          <span className="text-xs text-muted-foreground">Original</span>
        </>
      )}
    </Button>
  );
};