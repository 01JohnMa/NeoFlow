import { unstableSetRender } from './unstable-render';
export function renderToBody(element) {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const unmount = unstableSetRender()(element, container);
  return () => {
    var _a;
    unmount();
    (_a = container.parentNode) === null || _a === void 0 ? void 0 : _a.removeChild(container);
  };
}