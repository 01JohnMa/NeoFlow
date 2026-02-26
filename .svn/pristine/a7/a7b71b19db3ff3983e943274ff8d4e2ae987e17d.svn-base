import { useMemoizedFn } from 'ahooks';
import { DownOutline, TextDeletionOutline } from 'antd-mobile-icons';
import classNames from 'classnames';
import React, { useMemo, useRef } from 'react';
import { withNativeProps } from '../../utils/native-props';
import { shuffle } from '../../utils/shuffle';
import { mergeProps } from '../../utils/with-default-props';
import { useConfig } from '../config-provider';
import Popup from '../popup';
import SafeArea from '../safe-area';
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
export const NumberKeyboard = p => {
  const props = mergeProps(defaultProps, p);
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
  } = useConfig();
  const keyboardRef = useRef(null);
  const keys = useMemo(() => {
    const defaultKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9'];
    const keyList = randomOrder ? shuffle(defaultKeys) : defaultKeys;
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
  const timeoutRef = useRef(-1);
  const intervalRef = useRef(-1);
  const onDelete = useMemoizedFn(() => {
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
    return React.createElement("div", {
      className: classNames(`${classPrefix}-header`, {
        [`${classPrefix}-header-with-title`]: !!title
      })
    }, !!title && React.createElement("div", {
      className: `${classPrefix}-title`,
      "aria-label": title
    }, title), showCloseButton && React.createElement("span", {
      className: `${classPrefix}-header-close-button`,
      onClick: () => {
        var _a;
        (_a = props.onClose) === null || _a === void 0 ? void 0 : _a.call(props);
      },
      role: 'button',
      title: locale.common.close,
      tabIndex: -1
    }, React.createElement(DownOutline, null)));
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
    const className = classNames(`${classPrefix}-key`, {
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
    return React.createElement("div", Object.assign({
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
    }, ariaProps), isBackspace ? React.createElement(TextDeletionOutline, null) : realKey);
  };
  return React.createElement(Popup, {
    visible: visible,
    getContainer: getContainer,
    mask: false,
    afterClose: props.afterClose,
    afterShow: props.afterShow,
    className: `${classPrefix}-popup`,
    stopPropagation: props.stopPropagation,
    destroyOnClose: props.destroyOnClose,
    forceRender: props.forceRender
  }, withNativeProps(props, React.createElement("div", {
    ref: keyboardRef,
    className: classPrefix,
    onMouseDown: e => {
      // 点击键盘时，不会触发页面已聚焦元素（如输入框）的 blur 事件
      e.preventDefault();
    }
  }, renderHeader(), React.createElement("div", {
    className: `${classPrefix}-wrapper`
  }, React.createElement("div", {
    className: classNames(`${classPrefix}-main`, {
      [`${classPrefix}-main-confirmed-style`]: !!confirmText
    })
  }, keys.map(renderKey)), !!confirmText && React.createElement("div", {
    className: `${classPrefix}-confirm`
  }, React.createElement("div", {
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
  }, React.createElement(TextDeletionOutline, null)), React.createElement("div", {
    className: `${classPrefix}-key ${classPrefix}-key-extra ${classPrefix}-key-ok`,
    onClick: e => onKeyPress(e, 'OK'),
    role: 'button',
    tabIndex: -1,
    "aria-label": confirmText
  }, confirmText))), props.safeArea && React.createElement("div", {
    className: `${classPrefix}-footer`
  }, React.createElement(SafeArea, {
    position: 'bottom'
  })))));
};