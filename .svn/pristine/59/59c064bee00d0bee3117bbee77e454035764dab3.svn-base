"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.VirtualInput = void 0;
var _ahooks = require("ahooks");
var _antdMobileIcons = require("antd-mobile-icons");
var _classnames = _interopRequireDefault(require("classnames"));
var _react = _interopRequireWildcard(require("react"));
var _nativeProps = require("../../utils/native-props");
var _usePropsValue = require("../../utils/use-props-value");
var _withDefaultProps = require("../../utils/with-default-props");
var _configProvider = require("../config-provider");
var _useClickOutside = _interopRequireDefault(require("./use-click-outside"));
function _getRequireWildcardCache(nodeInterop) { if (typeof WeakMap !== "function") return null; var cacheBabelInterop = new WeakMap(); var cacheNodeInterop = new WeakMap(); return (_getRequireWildcardCache = function (nodeInterop) { return nodeInterop ? cacheNodeInterop : cacheBabelInterop; })(nodeInterop); }
function _interopRequireWildcard(obj, nodeInterop) { if (!nodeInterop && obj && obj.__esModule) { return obj; } if (obj === null || typeof obj !== "object" && typeof obj !== "function") { return { default: obj }; } var cache = _getRequireWildcardCache(nodeInterop); if (cache && cache.has(obj)) { return cache.get(obj); } var newObj = {}; var hasPropertyDescriptor = Object.defineProperty && Object.getOwnPropertyDescriptor; for (var key in obj) { if (key !== "default" && Object.prototype.hasOwnProperty.call(obj, key)) { var desc = hasPropertyDescriptor ? Object.getOwnPropertyDescriptor(obj, key) : null; if (desc && (desc.get || desc.set)) { Object.defineProperty(newObj, key, desc); } else { newObj[key] = obj[key]; } } } newObj.default = obj; if (cache) { cache.set(obj, newObj); } return newObj; }
function _interopRequireDefault(obj) { return obj && obj.__esModule ? obj : { default: obj }; }
const classPrefix = 'adm-virtual-input';
const defaultProps = {
  defaultValue: '',
  cursor: {
    movable: false
  }
};
const VirtualInput = (0, _react.forwardRef)((props, ref) => {
  const {
    locale,
    input: componentConfig = {}
  } = (0, _configProvider.useConfig)();
  const mergedProps = (0, _withDefaultProps.mergeProps)(defaultProps, componentConfig, props);
  const [value, setValue] = (0, _usePropsValue.usePropsValue)(mergedProps);
  const rootRef = (0, _react.useRef)(null);
  const contentRef = (0, _react.useRef)(null);
  const [hasFocus, setHasFocus] = (0, _react.useState)(false);
  const [caretPosition, setCaretPosition] = (0, _react.useState)(value.length); // 光标位置，从 0 开始，如值是 2 则表示光标在顺序下标为 2 的数字之前
  const keyboardDataRef = (0, _react.useRef)({}); // 临时记录虚拟键盘输入，在下次更新时用于判断光标位置如何调整
  const touchDataRef = (0, _react.useRef)(); // 记录上一次 touch 时的坐标位置
  const charRef = (0, _react.useRef)(null); // 第一个字符的 DOM
  const charWidthRef = (0, _react.useRef)(0); // 单个字符宽度
  const caretRef = (0, _react.useRef)(null); // 光标的 DOM
  const [isCaretDragging, setIsCaretDragging] = (0, _react.useState)(false);
  const touchMoveTimeoutRef = (0, _react.useRef)();
  const clearIcon = (0, _withDefaultProps.mergeProp)(_react.default.createElement(_antdMobileIcons.CloseCircleFill, null), componentConfig.clearIcon, props.clearIcon);
  function scrollToEnd() {
    const content = contentRef.current;
    if (!content) {
      return;
    }
    content.scrollLeft = content.clientWidth;
  }
  (0, _react.useEffect)(() => {
    // 记录单个字符的宽度，用于光标移动时的计算
    if (charRef.current) {
      charWidthRef.current = charRef.current.getBoundingClientRect().width;
    }
  }, [value]);
  (0, _react.useEffect)(() => {
    // 经过外部受控逻辑后，再调整光标位置，如果受控逻辑改动了值则光标放到最后
    if (value === keyboardDataRef.current.newValue) {
      if (keyboardDataRef.current.mode === 'input') {
        setCaretPosition(c => c + 1);
      } else if (keyboardDataRef.current.mode === 'delete') {
        setCaretPosition(c => c - 1);
      }
    } else {
      setCaretPosition(value.length);
    }
  }, [value]);
  (0, _ahooks.useIsomorphicLayoutEffect)(() => {
    scrollToEnd();
  }, [value]);
  (0, _react.useEffect)(() => {
    if (hasFocus) {
      scrollToEnd();
    }
  }, [hasFocus]);
  (0, _react.useImperativeHandle)(ref, () => ({
    focus: () => {
      var _a;
      (_a = contentRef.current) === null || _a === void 0 ? void 0 : _a.focus();
    },
    blur: () => {
      var _a;
      (_a = contentRef.current) === null || _a === void 0 ? void 0 : _a.blur();
      setBlur();
    }
  }));
  function setFocus() {
    var _a;
    if (hasFocus) return;
    setHasFocus(true);
    (_a = mergedProps.onFocus) === null || _a === void 0 ? void 0 : _a.call(mergedProps);
  }
  function setBlur() {
    var _a;
    if (!hasFocus) return;
    setHasFocus(false);
    (_a = mergedProps.onBlur) === null || _a === void 0 ? void 0 : _a.call(mergedProps);
  }
  (0, _useClickOutside.default)(() => {
    setBlur();
  }, rootRef, !!mergedProps.keyboard);
  const keyboard = mergedProps.keyboard;
  const keyboardElement = keyboard && _react.default.cloneElement(keyboard, {
    onInput: v => {
      var _a, _b;
      const newValue = value.substring(0, caretPosition) + v + value.substring(caretPosition);
      // 临时记录，用于后续光标位置
      keyboardDataRef.current = {
        newValue,
        mode: 'input'
      };
      setValue(newValue);
      (_b = (_a = keyboard.props).onInput) === null || _b === void 0 ? void 0 : _b.call(_a, v);
    },
    onDelete: () => {
      var _a, _b;
      if (caretPosition === 0) return;
      const newValue = value.substring(0, caretPosition - 1) + value.substring(caretPosition);
      // 临时记录，用于后续光标位置
      keyboardDataRef.current = {
        newValue,
        mode: 'delete'
      };
      setValue(newValue);
      (_b = (_a = keyboard.props).onDelete) === null || _b === void 0 ? void 0 : _b.call(_a);
    },
    visible: hasFocus,
    onClose: () => {
      var _a, _b, _c;
      const activeElement = document.activeElement;
      if (activeElement === contentRef.current) {
        // 点击 NumberKeyboard 的确认和关闭时不会触发输入框的 blur 事件，手动调用让其失焦，否则之后无法 focus
        (_a = contentRef.current) === null || _a === void 0 ? void 0 : _a.blur();
      }
      setBlur();
      (_c = (_b = keyboard.props).onClose) === null || _c === void 0 ? void 0 : _c.call(_b);
    },
    getContainer: null
  });
  // 点击输入框时，将光标置于最后
  const setCaretPositionToEnd = e => {
    var _a, _b, _c;
    if (mergedProps.disabled) {
      return;
    }
    if (caretPosition !== value.length) {
      setCaretPosition(value.length);
      (_b = (_a = mergedProps.cursor) === null || _a === void 0 ? void 0 : _a.onMove) === null || _b === void 0 ? void 0 : _b.call(_a, value.length);
    }
    (_c = mergedProps.onClick) === null || _c === void 0 ? void 0 : _c.call(mergedProps, e);
    setFocus();
  };
  // 点击单个字符时，根据点击位置置于字符前或后
  const changeCaretPosition = index => e => {
    var _a, _b, _c;
    if (mergedProps.disabled || !((_a = mergedProps.cursor) === null || _a === void 0 ? void 0 : _a.movable)) return;
    e.stopPropagation();
    const rect = e.target.getBoundingClientRect();
    const midX = rect.left + rect.width / 2;
    const clickX = e.clientX;
    // 点击区域是否偏右
    const isRight = clickX > midX;
    const newCaretPosition = isRight ? index + 1 : index;
    setCaretPosition(newCaretPosition);
    (_c = (_b = mergedProps.cursor) === null || _b === void 0 ? void 0 : _b.onMove) === null || _c === void 0 ? void 0 : _c.call(_b, newCaretPosition);
  };
  // 在光标附近 touchmove 时也可以调整光标位置
  const handleTouchStart = e => {
    var _a;
    if (mergedProps.disabled || !((_a = mergedProps.cursor) === null || _a === void 0 ? void 0 : _a.movable)) return;
    if (!caretRef.current) return;
    const touch = e.touches[0];
    const caretRect = caretRef.current.getBoundingClientRect();
    const distance = Math.abs(touch.clientX - (caretRect.left + caretRect.width / 2));
    if (distance < 20) {
      // 20px 阈值可调整
      touchDataRef.current = {
        startX: touch.clientX,
        startCaretPosition: caretPosition
      };
    } else {
      touchDataRef.current = null;
    }
  };
  const handleTouchMove = e => {
    var _a, _b, _c;
    if (!touchDataRef.current || !((_a = mergedProps.cursor) === null || _a === void 0 ? void 0 : _a.movable)) return;
    setIsCaretDragging(true);
    const touch = e.touches[0];
    const deltaX = touch.clientX - touchDataRef.current.startX;
    const charWidth = charWidthRef.current;
    const moveChars = Math.round(deltaX / charWidth);
    let newCaretPosition = touchDataRef.current.startCaretPosition + moveChars;
    // 边界处理
    newCaretPosition = Math.max(0, Math.min(newCaretPosition, value.length));
    setCaretPosition(newCaretPosition);
    (_c = (_b = mergedProps.cursor) === null || _b === void 0 ? void 0 : _b.onMove) === null || _c === void 0 ? void 0 : _c.call(_b, newCaretPosition);
    // 防止 touchend 不触发
    if (touchMoveTimeoutRef.current) {
      clearTimeout(touchMoveTimeoutRef.current);
    }
    touchMoveTimeoutRef.current = setTimeout(() => {
      setIsCaretDragging(false);
      touchMoveTimeoutRef.current = null;
    }, 500);
  };
  const handleTouchEnd = () => {
    touchDataRef.current = null;
    setIsCaretDragging(false);
    if (touchMoveTimeoutRef.current) {
      clearTimeout(touchMoveTimeoutRef.current);
      touchMoveTimeoutRef.current = null;
    }
  };
  const chars = (value + '').split('');
  return (0, _nativeProps.withNativeProps)(mergedProps, _react.default.createElement("div", {
    ref: rootRef,
    className: (0, _classnames.default)(classPrefix, {
      [`${classPrefix}-disabled`]: mergedProps.disabled,
      [`${classPrefix}-caret-dragging`]: isCaretDragging,
      [`${classPrefix}-focused`]: hasFocus
    })
  }, _react.default.createElement("div", {
    className: `${classPrefix}-content`,
    ref: contentRef,
    "aria-disabled": mergedProps.disabled,
    "aria-label": value ? undefined : mergedProps.placeholder,
    role: 'textbox',
    tabIndex: mergedProps.disabled ? undefined : 0,
    // note: 这里增加 onFocus 有两个目的：
    // 1. 在安卓 talkback 模式下，role=textbox 的元素双击后只会触发 focus 而非 click
    // 2. 处理 content 框点击、单个字符点击时，不用再额外处理 focus 逻辑，因为 focus 事件会先触发
    onFocus: setFocus,
    onClick: setCaretPositionToEnd,
    onTouchStart: handleTouchStart,
    onTouchMove: handleTouchMove,
    onTouchEnd: handleTouchEnd
  }, _react.default.createElement("span", {
    className: `${classPrefix}-trap`
  }), chars.slice(0, caretPosition).map((i, index) => _react.default.createElement("span", {
    ref: index === 0 ? charRef : undefined,
    key: index,
    onClick: changeCaretPosition(index)
  }, i)), _react.default.createElement("div", {
    className: `${classPrefix}-caret-container`
  }, hasFocus && _react.default.createElement("div", {
    ref: caretRef,
    className: `${classPrefix}-caret`
  })), chars.slice(caretPosition).map((i, index) => _react.default.createElement("span", {
    key: index,
    onClick: changeCaretPosition(index + caretPosition)
  }, i))), mergedProps.clearable && !!value && hasFocus && _react.default.createElement("div", {
    className: `${classPrefix}-clear`,
    onClick: e => {
      var _a;
      e.stopPropagation();
      setValue('');
      (_a = mergedProps.onClear) === null || _a === void 0 ? void 0 : _a.call(mergedProps);
    },
    role: 'button',
    "aria-label": locale.Input.clear
  }, clearIcon), [undefined, null, ''].includes(value) && _react.default.createElement("div", {
    className: `${classPrefix}-placeholder`
  }, mergedProps.placeholder), keyboardElement));
});
exports.VirtualInput = VirtualInput;