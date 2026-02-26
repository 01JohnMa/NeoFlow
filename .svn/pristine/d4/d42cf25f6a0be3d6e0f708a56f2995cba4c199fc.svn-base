import type { FC, ReactNode } from 'react';
import { NativeProps } from '../../utils/native-props';
import { CenterPopupProps } from '../center-popup';
import { Action } from './modal-action-button';
export declare type ModalProps = Pick<CenterPopupProps, 'afterClose' | 'afterShow' | 'bodyClassName' | 'bodyStyle' | 'destroyOnClose' | 'disableBodyScroll' | 'forceRender' | 'getContainer' | 'maskClassName' | 'maskStyle' | 'stopPropagation' | 'visible'> & {
    image?: string;
    header?: ReactNode;
    title?: ReactNode;
    content?: ReactNode;
    actions?: Action[];
    onAction?: (action: Action, index: number) => void | Promise<void>;
    onClose?: () => void;
    closeOnAction?: boolean;
    closeOnMaskClick?: boolean;
    showCloseButton?: boolean;
} & NativeProps<'--background-color' | '--border-radius' | '--max-width' | '--min-width' | '--z-index'>;
export declare const Modal: FC<ModalProps>;
