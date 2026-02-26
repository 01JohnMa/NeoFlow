"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.NumberKeyboard = void 0;
var _ahooks = require("ahooks");
var _antdMobileIcons = require("antd-mobile-icons");
var _classnames = _interopRequireDefault(require("classnames"));
var _react = _interopRequireWildcard(require("react"));
var _nativeProps = require("../../utils/native-props");
var _shuffle = require("../../utils/shuffle");
var _withDefaultProps = require("../../utils/with-default-props");
var _configProvider = require("../config-provider");
var _popup = _interopRequireDefault(require("../popup"));
var _safeArea = _interopRequireDefault(require("../safe-area"));
function _getRequireWildcardCache(nodeInterop) { if (typeof WeakMap !== "function") return null; var cacheBabelInterop = new WeakMap(); var cacheNodeInterop = new WeakMap(); return (_getRequireWildcardCache = function (nodeInterop) { return nodeInterop ? cacheNodeInterop : cacheBabelInterop; })(nodeInterop); }
function _interopRequireWildcard(obj, nodeInterop) { if (!nodeInterop && obj && obj.__esModule) { return obj; } if (obj === null || typeof obj !== "object" && typeof obj !== "function") { return { default: obj }; } var cache = _getRequireWildcardCache(nodeInterop); if (cache && cache.has(obj)) { return cache.get(obj); } var newObj = {}; var hasPropertyDescriptor = Object.defineProperty && Object.getOwnPropertyDescriptor; for (var key in obj) { if (key !== "default" && Object.prototype.hasOwnProperty.call(obj, key)) { var desc = hasPropertyDescriptor ? Object.getOwnPropertyDescriptor(obj, key) : null; if (desc && (desc.get || desc.set)) { Object.defineProperty(newObj, key, desc); } else { newObj[key] = obj[key]; } } } newObj.default = obj; if (cache) { cache.set(obj, newObj); } return newObj; }
function _interopRequireDefault(obj) { return obj && obj.__esModule ? obj : { default: obj }; }
const classPrefix = 'adm-number-keyboard';
const defaultProps = {
  defaultVisible: false,
  randomOrder: false,
  showCloseButton: true,
  confirmText: null,
  closeOnConfirm: true,
  safeArea: true,
  destroyOnClose: false,
  forceRender: false
};
const NumberKeyboard = p => {
  const props = (0, _withDefaultProps.mergeProps)(defaultProps, p);
  const {
    visible,
    title,
    getContainer,
    confirmText,
    customKey,
    randomOrder,
    showCloseButton,
    onInput
  } = props;
  const {
    locale
  } = (0, _configProvider.useConfig)();
  const keyboardRef = (0, _react.useRef)(null);
  const keys = (0, _react.useMemo)(() => {
    const defaultKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9'];
    const keyList = randomOrder ? (0, _shuffle.shuffle)(defaultKeys) : defaultKeys;
    const customKeys = Array.isArray(customKey) ? customKey : [customKey];
    keyList.push('0');
    if (confirmText) {
      if (customKeys.length === 2) {
        keyList.splice(9, 0, customKeys.pop());
      }
      keyList.push(customKeys[0] || '');
    } else {
      keyList.splice(9, 0, customKeys[0] || '');
      keyList.push(customKeys[1] || 'BACKSPACE');
    }
    return keyList;
  }, [customKey, confirmText, randomOrder, randomOrder && visible]);
  const timeoutRef = (0, _react.useRef)(-1);
  const intervalRef = (0, _react.useRef)(-1);
  const onDelete = (0, _ahooks.useMemoizedFn)(() => {
    var _a;
    (_a = props.onDelete) === null || _a === void 0 ? void 0 : _a.call(props);
  });
  const startContinueClear = () => {
    timeoutRef.current = window.setTimeout(() => {
      onDelete();
      intervalRef.current = window.setInterval(onDelete, 150);
    }, 700);
  };
  const stopContinueClear = () => {
    clearTimeout(timeoutRef.current);
    clearInterval(intervalRef.current);
  };
  const onKeyPress = (e, key) => {
    var _a, _b;
    switch (key) {
      case 'BACKSPACE':
        onDelete === null || onDelete === void 0 ? void 0 : onDelete();
        break;
      case 'OK':
        (_a = props.onConfirm) === null || _a === void 0 ? void 0 : _a.call(props);
        if (props.closeOnConfirm) {
          (_b = props.onClose) === null || _b === void 0 ? void 0 : _b.call(props);
        }
        break;
      default:
        // onInput should't be called when customKey doesn't exist
        if (key !== '') onInput === null || onInput === void 0 ? void 0 : onInput(key);
        break;
    }
  };
  const renderHeader = () => {
    if (!showCloseButton && !title) return null;
    return _react.default.createElement("div", {
      className: (0, _classnames.default)(`${classPrefix}-header`, {
        [`${classPrefix}-header-with-title`]: !!title
      })
    }, !!title && _react.default.createElement("div", {
      className: `${classPrefix}-title`,
      "aria-label": title
    }, title), showCloseButton && _react.default.createElement("span", {
      className: `${classPrefix}-header-close-button`,
      onClick: () => {
        var _a;
        (_a = props.onClose) === null || _a === void 0 ? void 0 : _a.call(props);
      },
      role: 'button',
      title: locale.common.close,
      tabIndex: -1
    }, _react.default.createElement(_antdMobileIcons.DownOutline, null)));
  };
  const onBackspaceTouchStart = () => {
    stopContinueClear();
    startContinueClear();
  };
  const onBackspaceTouchEnd = e => {
    e.preventDefault(); // 短按时，touchend 会阻止后续 click 事件触发，防止删除两次
    stopContinueClear();
    onKeyPress(e, 'BACKSPACE');
  };
  const renderKey = (key, index) => {
    const keyConfig = typeof key === 'string' ? {
      key,
      title: key
    } : key;
    const realKey = keyConfig.key;
    const isNumberKey = /^\d$/.test(realKey);
    const isBackspace = realKey === 'BACKSPACE';
    const title = isBackspace ? locale.NumberKeyboard.backspace : keyConfig.title;
    const className = (0, _classnames.default)(`${classPrefix}-key`, {
      [`${classPrefix}-key-number`]: isNumberKey,
      [`${classPrefix}-key-sign`]: !isNumberKey && realKey,
      [`${classPrefix}-key-mid`]: index === 9 && !!confirmText && keys.length < 12
    });
    const ariaProps = realKey ? {
      role: 'button',
      title,
      'aria-label': title,
      tabIndex: -1
    } : undefined;
    return _react.default.createElement("div", Object.assign({
      key: realKey,
      className: className,
      // 仅为  backspace 绑定，支持长按快速删除
      onTouchStart: isBackspace ? onBackspaceTouchStart : undefined,
      onTouchEnd: isBackspace ? onBackspaceTouchEnd : undefined,
      onTouchCancel: isBackspace ? stopContinueClear : undefined,
      // <div role="button" title="1" onTouchEnd={e => {}}>1</div> 安卓上 talback 可读不可点
      // see https://ua-gilded-eef7f9.netlify.app/grid-button-bug.html
      // 所以普通按钮绑定 click 事件，而 backspace 仍然额外绑定 touch 事件支持长按删除
      // backspace touchend 时会 preventDefault 阻止其后续 click 事件
      onClick: e => {
        stopContinueClear();
        onKeyPress(e, realKey);
      }
    }, ariaProps), isBackspace ? _react.default.createElement(_antdMobileIcons.TextDeletionOutline, null) : realKey);
  };
  return _react.default.createElement(_popup.default, {
    visible: visible,
    getContainer: getContainer,
    mask: false,
    afterClose: props.afterClose,
    afterShow: props.afterShow,
    className: `${classPrefix}-popup`,
    stopPropagation: props.stopPropagation,
    destroyOnClose: props.destroyOnClose,
    forceRender: props.forceRender
  }, (0, _nativeProps.withNativeProps)(props, _react.default.createElement("div", {
    ref: keyboardRef,
    className: classPrefix,
    onMouseDown: e => {
      // 点击键盘时，不会触发页面已聚焦元素（如输入框）的 blur 事件
      e.preventDefault();
    }
  }, renderHeader(), _react.default.createElement("div", {
    className: `${classPrefix}-wrapper`
  }, _react.default.createElement("div", {
    className: (0, _classnames.default)(`${classPrefix}-main`, {
      [`${classPrefix}-main-confirmed-style`]: !!confirmText
    })
  }, keys.map(renderKey)), !!confirmText && _react.default.createElement("div", {
    className: `${classPrefix}-confirm`
  }, _react.default.createElement("div", {
    className: `${classPrefix}-key ${classPrefix}-key-extra ${classPrefix}-key-bs`,
    onTouchStart: onBackspaceTouchStart,
    onTouchEnd: onBackspaceTouchEnd,
    onTouchCancel: stopContinueClear,
    onClick: e => {
      stopContinueClear();
      onKeyPress(e, 'BACKSPACE');
    },
    onContextMenu: e => {
      // Long press should not trigger native context menu
      e.preventDefault();
    },
    title: locale.NumberKeyboard.backspace,
    role: 'button',
    tabIndex: -1
  }, _react.default.createElement(_antdMobileIcons.TextDeletionOutline, null)), _react.default.createElement("div", {
    className: `${classPrefix}-key ${classPrefix}-key-extra ${classPrefix}-key-ok`,
    onClick: e => onKeyPress(e, 'OK'),
    role: 'button',
    tabIndex: -1,
    "aria-label": confirmText
  }, confirmText))), props.safeArea && _react.default.createElement("div", {
    className: `${classPrefix}-footer`
  }, _react.default.createElement(_safeArea.default, {
    position: 'bottom'
  })))));
};
exports.NumberKeyboard = NumberKeyboard;