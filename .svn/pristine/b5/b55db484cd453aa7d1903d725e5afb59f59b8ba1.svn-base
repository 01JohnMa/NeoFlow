"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.default = useInputHandleKeyDown;
function useInputHandleKeyDown({
  onEnterPress,
  onKeyDown
}) {
  const handleKeydown = e => {
    if (onEnterPress && (e.code === 'Enter' || e.keyCode === 13)) {
      onEnterPress(e);
    }
    onKeyDown === null || onKeyDown === void 0 ? void 0 : onKeyDown(e);
  };
  return handleKeydown;
}