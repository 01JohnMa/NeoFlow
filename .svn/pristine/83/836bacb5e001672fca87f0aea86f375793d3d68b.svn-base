import { useCallback } from 'react';
import { useConfig } from '../config-provider';
export default function useRenderLabel(renderLabel) {
  const {
    locale
  } = useConfig();
  return useCallback((type, data, info) => {
    if (renderLabel) {
      return renderLabel(type, data, info);
    }
    // Default render
    switch (type) {
      case 'minute':
      case 'second':
      case 'hour':
        return ('0' + data.toString()).slice(-2);
      case 'now':
        return locale.DatePicker.tillNow;
      default:
        return data.toString();
    }
  }, [renderLabel]);
}