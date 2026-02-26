"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.Wrapper = void 0;
var _findDOMNode = _interopRequireWildcard(require("rc-util/lib/Dom/findDOMNode"));
var _ref = require("rc-util/lib/ref");
var React = _interopRequireWildcard(require("react"));
function _getRequireWildcardCache(nodeInterop) { if (typeof WeakMap !== "function") return null; var cacheBabelInterop = new WeakMap(); var cacheNodeInterop = new WeakMap(); return (_getRequireWildcardCache = function (nodeInterop) { return nodeInterop ? cacheNodeInterop : cacheBabelInterop; })(nodeInterop); }
function _interopRequireWildcard(obj, nodeInterop) { if (!nodeInterop && obj && obj.__esModule) { return obj; } if (obj === null || typeof obj !== "object" && typeof obj !== "function") { return { default: obj }; } var cache = _getRequireWildcardCache(nodeInterop); if (cache && cache.has(obj)) { return cache.get(obj); } var newObj = {}; var hasPropertyDescriptor = Object.defineProperty && Object.getOwnPropertyDescriptor; for (var key in obj) { if (key !== "default" && Object.prototype.hasOwnProperty.call(obj, key)) { var desc = hasPropertyDescriptor ? Object.getOwnPropertyDescriptor(obj, key) : null; if (desc && (desc.get || desc.set)) { Object.defineProperty(newObj, key, desc); } else { newObj[key] = obj[key]; } } } newObj.default = obj; if (cache) { cache.set(obj, newObj); } return newObj; }
class LegacyWrapper extends React.Component {
  constructor() {
    super(...arguments);
    this.element = null;
  }
  componentDidMount() {
    this.componentDidUpdate();
  }
  componentDidUpdate() {
    // eslint-disable-next-line
    const node = (0, _findDOMNode.default)(this);
    if (node instanceof Element) {
      this.element = node;
    } else {
      this.element = null;
    }
  }
  render() {
    return this.props.children;
  }
}
const Wrapper = React.forwardRef(({
  children
}, ref) => {
  const elementRef = React.useRef(null);
  const legacyWrapperRef = React.createRef();
  const child = React.Children.only(children);
  const canUseRef = (0, _ref.supportRef)(children);
  const getElement = () => {
    var _a;
    if (canUseRef) {
      return (0, _findDOMNode.getDOM)(elementRef.current);
    }
    return (_a = legacyWrapperRef.current) === null || _a === void 0 ? void 0 : _a.element;
  };
  React.useImperativeHandle(ref, () => ({
    element: getElement()
  }));
  const composedRef = (0, _ref.composeRef)(elementRef, (0, _ref.getNodeRef)(child));
  return canUseRef ? React.cloneElement(child, {
    ref: composedRef
  }) : React.createElement(LegacyWrapper, {
    ref: legacyWrapperRef
  }, child);
});
exports.Wrapper = Wrapper;