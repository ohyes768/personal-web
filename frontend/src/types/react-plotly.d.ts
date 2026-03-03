/**
 * react-plotly.js 类型声明
 */
declare module 'react-plotly.js' {
  import { Component } from 'react';

  export interface PlotProps {
    data: any[];
    layout?: any;
    config?: any;
    style?: React.CSSProperties;
    className?: string;
    useResizeHandler?: boolean;
    onInitialized?: () => void;
    onUpdate?: () => void;
    onError?: (error: Error) => void;
  }

  export default class Plot extends Component<PlotProps> {}
}
