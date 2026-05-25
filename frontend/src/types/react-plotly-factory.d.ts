declare module 'react-plotly.js/factory.js' {
  import type { PlotParams } from 'react-plotly.js'
  import type { ComponentType } from 'react'

  interface FactoryModule {
    default: (plotly: object) => ComponentType<PlotParams>
  }

  const createPlotlyComponent:
    | ((plotly: object) => ComponentType<PlotParams>)
    | FactoryModule

  export default createPlotlyComponent
}
