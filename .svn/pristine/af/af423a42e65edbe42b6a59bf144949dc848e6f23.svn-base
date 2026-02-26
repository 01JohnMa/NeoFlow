import React from 'react';
import { withNativeProps } from '../../utils/native-props';
import { mergeProps } from '../../utils/with-default-props';
import Image from '../image';
import { Fallback } from './fallback';
const classPrefix = 'adm-avatar';
const defaultProps = {
  fallback: React.createElement(Fallback, null),
  fit: 'cover'
};
export const Avatar = p => {
  var _a;
  const props = mergeProps(defaultProps, p);
  const mergedSrc = ((_a = props.src) === null || _a === void 0 ? void 0 : _a.trim()) || undefined;
  return withNativeProps(props, React.createElement(Image, {
    className: classPrefix,
    src: mergedSrc,
    fallback: props.fallback,
    placeholder: props.fallback,
    alt: props.alt,
    lazy: props.lazy,
    fit: props.fit,
    onClick: props.onClick,
    onError: props.onError,
    onLoad: props.onLoad
  }));
};