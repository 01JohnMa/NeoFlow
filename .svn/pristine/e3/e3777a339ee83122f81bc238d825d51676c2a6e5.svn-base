"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.withStopPropagation = withStopPropagation;
var _react = _interopRequireDefault(require("react"));
function _interopRequireDefault(obj) { return obj && obj.__esModule ? obj : { default: obj }; }
const eventToPropRecord = {
  'click': 'onClick',
  'touchstart': 'onTouchStart'
};
function withStopPropagation(events, element) {
  const props = Object.assign({}, element.props);
  for (const key of events) {
    const prop = eventToPropRecord[key];
    props[prop] = function (e) {
      var _a, _b;
      e.stopPropagation();
      // react <=16 事件绑定在 document，因此上面的 stopPropagation 无法阻止事件冒泡到用原生方式监听的 document 的事件回调中
      // 增加 stopImmediatePropagation 可以阻止事件在**后绑定**的 document 上的回调执行
      // 专用于解决 VirtualInput useClickOutside 的问题
      // react >=17 则无此问题，事件会绑定在 React 根节点上
      e.nativeEvent.stopImmediatePropagation();
      (_b = (_a = element.props)[prop]) === null || _b === void 0 ? void 0 : _b.call(_a, e);
    };
  }
  return _react.default.cloneElement(element, props);
}