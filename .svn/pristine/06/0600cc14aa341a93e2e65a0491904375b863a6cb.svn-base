import type { FC } from 'react';
import { NativeProps } from '../../utils/native-props';
import { PopupProps } from '../popup';
declare type CustomKeyType = string | {
    key: string;
    title: string;
};
export declare type NumberKeyboardProps = {
    visible?: boolean;
    title?: string;
    confirmText?: string | null;
    customKey?: CustomKeyType | CustomKeyType[];
    randomOrder?: boolean;
    showCloseButton?: boolean;
    onInput?: (v: string) => void;
    onDelete?: () => void;
    onClose?: () => void;
    onConfirm?: () => void;
    closeOnConfirm?: boolean;
    safeArea?: boolean;
} & Pick<PopupProps, 'afterClose' | 'afterShow' | 'getContainer' | 'destroyOnClose' | 'forceRender' | 'stopPropagation'> & NativeProps<'--adm-safe-area-multiple'>;
export declare const NumberKeyboard: FC<NumberKeyboardProps>;
export {};
