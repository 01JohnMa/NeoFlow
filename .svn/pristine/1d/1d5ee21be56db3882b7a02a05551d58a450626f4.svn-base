import React, { ReactNode, RefObject } from 'react';
export declare type SlidesType = {
    images: string[];
    onTap?: () => void;
    maxZoom: number;
    defaultIndex: number;
    onIndexChange?: (index: number) => void;
    imageRender?: (image: string, { ref, index }: {
        ref: RefObject<HTMLImageElement>;
        index: number;
    }) => ReactNode;
};
export declare type SlidesRef = {
    swipeTo: (index: number, immediate?: boolean) => void;
};
export declare const Slides: React.ForwardRefExoticComponent<SlidesType & React.RefAttributes<SlidesRef>>;
