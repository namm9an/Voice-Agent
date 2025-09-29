import React, { useEffect } from 'react';

const ErrorDisplay = ({ error, onRetry, autoDismiss = false, dismissTime = 5000 }) => {
  useEffect(() => {
    if (autoDismiss && error) {
      const t = setTimeout(() => {
        if (onRetry) onRetry();
      }, dismissTime);
      return () => clearTimeout(t);
    }
  }, [autoDismiss, dismissTime, error, onRetry]);

  if (!error) return null;

  const isWarning = error.type === 'warning' || error.type === 'info';

  return (
    <div className={`error-display ${isWarning ? 'warning' : 'error'}`} role="alert">
      <div className="error-message">{error.message}</div>
      <div className="error-actions">
        {onRetry && error.canRetry && (
          <button onClick={onRetry}>Retry</button>
        )}
      </div>
    </div>
  );
};

export default ErrorDisplay;

