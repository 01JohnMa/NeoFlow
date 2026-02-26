import findDOMNode, { getDOM } from 'rc-util/lib/Dom/findDOMNode';
import { composeRef, getNodeRef, supportRef } from 'rc-util/lib/ref';
import * as React from 'react';
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
    const node = findDOMNode(this);
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
export const Wrapper = React.forwardRef(({
  children
}, ref) => {
  const elementRef = React.useRef(null);
  const legacyWrapperRef = React.createRef();
  const child = React.Children.only(children);
  const canUseRef = supportRef(children);
  const getElement = () => {
    var _a;
    if (canUseRef) {
      return getDOM(elementRef.current);
    }
    return (_a = legacyWrapperRef.current) === null || _a === void 0 ? void 0 : _a.element;
  };
  React.useImperativeHandle(ref, () => ({
    element: getElement()
  }));
  const composedRef = composeRef(elementRef, getNodeRef(child));
  return canUseRef ? React.cloneElement(child, {
    ref: composedRef
  }) : React.createElement(LegacyWrapper, {
    ref: legacyWrapperRef
  }, child);
});