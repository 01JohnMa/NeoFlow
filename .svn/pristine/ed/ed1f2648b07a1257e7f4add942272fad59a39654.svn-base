"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.renderToBody = renderToBody;
var _unstableRender = require("./unstable-render");
function renderToBody(element) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const unmount = (0, _unstableRender.unstableSetRender)()(element, container);
  return () => {
    var _a;
    unmount();
    (_a = container.parentNode) === null || _a === void 0 ? void 0 : _a.removeChild(container);
  };
}