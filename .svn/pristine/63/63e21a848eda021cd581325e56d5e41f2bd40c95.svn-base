import type { FC, ReactNode } from 'react';
import React from 'react';
import { NativeProps } from '../../utils/native-props';
import { PropagationEvent } from '../../utils/with-stop-propagation';
export declare type EllipsisProps = {
    content: string;
    direction?: 'start' | 'end' | 'middle';
    rows?: number;
    expandText?: ReactNode;
    collapseText?: ReactNode;
    stopPropagationForActionButtons?: PropagationEvent[];
    onContentClick?: (e: React.MouseEvent<HTMLDivElement, MouseEvent>) => void;
    defaultExpanded?: boolean;
    onExpand?: (expanded: boolean, info: {
        event: React.MouseEvent<HTMLAnchorElement, MouseEvent>;
    }) => void;
} & NativeProps;
export declare const Ellipsis: FC<EllipsisProps>;
