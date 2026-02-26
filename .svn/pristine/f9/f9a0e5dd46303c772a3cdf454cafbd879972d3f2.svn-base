"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.default = useRenderLabel;
var _react = require("react");
var _configProvider = require("../config-provider");
function useRenderLabel(renderLabel) {
  const {
    locale
  } = (0, _configProvider.useConfig)();
  return (0, _react.useCallback)((type, data, info) => {
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